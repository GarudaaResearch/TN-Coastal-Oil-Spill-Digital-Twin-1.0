"""
Oil Spill Simulation Engine
============================
Implements a 2D Advection-Diffusion-Decay PDE for oil concentration:

    ∂C/∂t = D∇²C  -  u·∇C  -  λC  +  S(x,y,t)

Where:
    C(x,y,t)  – oil surface concentration (kg/m²)
    D         – turbulent diffusivity (m²/s) [Fay's spreading law calibrated]
    u, v      – current velocity (m/s) from ocean model
    λ         – natural decay/evaporation rate (1/s)
    S         – spill source term (kg/m²/s)

Numerical scheme: Operator-splitting
  - Diffusion : explicit central-difference (Δt chosen for stability)
  - Advection : upwind scheme (conservative, stable for |u|Δt/Δx ≤ 1)
  - Decay     : analytical exponential

Shoreline interaction: reflective BC at land mask boundaries.
High-impact zones: sensitivity amplification factor applied to display only
                   (does not alter physics, but flags for priority response).

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from .ocean_model import OceanEnvironment, GRID_W, GRID_H, DX, DY


# ─────────────────────────── Physical Constants ─────────────────────────────
DIFFUSIVITY_BASE   = 2.0        # m²/s  (turbulent horizontal diffusivity)
DECAY_RATE         = 2.5e-6     # 1/s   ≈ 20% evaporation/decay per day
WIND_DRIFT_FACTOR  = 0.035      # Leeway: 3.5% of wind speed drives surface oil
DENSITY_OIL        = 880.0      # kg/m³ (crude oil)
MAX_CONC           = 50.0       # kg/m² (saturation, for display clamping)
DETECTION_THRESHOLD = 0.05      # kg/m² – triggers alert


@dataclass
class SpillEvent:
    row: int
    col: int
    total_mass_kg: float
    release_rate_kg_s: float    # kg/s
    t_start: float
    t_end: Optional[float] = None   # None = continuous
    active: bool = True


class OilSpillEngine:
    """
    Manages oil concentration grid and advances the PDE each timestep.
    Supports multiple simultaneous spill sources.
    """

    def __init__(self, ocean: OceanEnvironment):
        self.ocean = ocean
        self.C = np.zeros((GRID_H, GRID_W), dtype=np.float64)    # concentration kg/m²
        self.spills: List[SpillEvent] = []
        self.total_oil_released_kg = 0.0
        self.total_oil_removed_kg  = 0.0
        self._history_area: List[float] = []
        self._history_mass: List[float] = []

    # ─────────────────────── Spill Management ──────────────────────────────

    def add_spill(self, row: int, col: int,
                  total_mass_kg: float = 5000.0,
                  release_rate_kg_s: float = 0.5) -> SpillEvent:
        ev = SpillEvent(
            row=row, col=col,
            total_mass_kg=total_mass_kg,
            release_rate_kg_s=release_rate_kg_s,
            t_start=self.ocean.t
        )
        self.spills.append(ev)
        return ev

    def _apply_sources(self, dt: float):
        """Inject oil from active spill events."""
        for spill in self.spills:
            if not spill.active:
                continue
            if self.total_oil_released_kg >= spill.total_mass_kg:
                spill.active = False
                continue
            injected = spill.release_rate_kg_s * dt / (DX * DY)   # kg/m²
            self.C[spill.row, spill.col] += injected
            self.total_oil_released_kg += injected * DX * DY

    # ─────────────────────── PDE Operators ─────────────────────────────────

    def _diffusion_step(self, dt: float, D: float, mask: np.ndarray):
        """
        Explicit central-difference Laplacian.
        Stability criterion: D·dt / dx² ≤ 0.5  → dt ≤ 0.5·dx²/D
        """
        C = self.C
        lap = (
            np.roll(C, -1, axis=1) + np.roll(C, 1, axis=1) - 2 * C
        ) / DX**2 + (
            np.roll(C, -1, axis=0) + np.roll(C, 1, axis=0) - 2 * C
        ) / DY**2
        dC = D * lap * dt
        self.C = np.maximum(0.0, C + dC * mask)

    def _advection_step(self, u: np.ndarray, v: np.ndarray,
                        dt: float, mask: np.ndarray):
        """
        First-order upwind scheme (donor-cell).
        Each cell donates concentration in the downwind direction.
        """
        C = self.C.copy()
        dC = np.zeros_like(C)

        # x-advection (u → east positive)
        u_pos = np.maximum(u, 0)
        u_neg = np.minimum(u, 0)
        dC -= (u_pos * (C - np.roll(C, 1, axis=1)) / DX +
               u_neg * (np.roll(C, -1, axis=1) - C) / DX) * dt

        # y-advection (v → north positive)
        v_pos = np.maximum(v, 0)
        v_neg = np.minimum(v, 0)
        dC -= (v_pos * (C - np.roll(C, 1, axis=0)) / DY +
               v_neg * (np.roll(C, -1, axis=0) - C) / DY) * dt

        self.C = np.maximum(0.0, (C + dC) * mask)

    def _decay_step(self, dt: float):
        """Analytical exponential decay for evaporation/biodegradation."""
        self.C *= np.exp(-DECAY_RATE * dt)

    # ─────────────────────── Main Step ─────────────────────────────────────

    def step(self) -> None:
        dt = self.ocean.dt
        mask = self.ocean.land_mask.astype(np.float64)

        # Operator splitting: source → advection → diffusion → decay
        self._apply_sources(dt)

        u, v = self.ocean.get_current_field()
        wu, wv = self.ocean.get_wind_forcing()

        # Effective surface velocity = ocean current + wind drift
        u_eff = u.astype(np.float64) + WIND_DRIFT_FACTOR * wu
        v_eff = v.astype(np.float64) + WIND_DRIFT_FACTOR * wv

        # CFL-based sub-stepping for advection stability
        max_vel = max(np.max(np.abs(u_eff)), np.max(np.abs(v_eff)), 1e-6)
        cfl_dt  = 0.9 * min(DX, DY) / max_vel
        n_sub   = max(1, int(np.ceil(dt / cfl_dt)))
        sub_dt  = dt / n_sub

        for _ in range(n_sub):
            self._advection_step(u_eff, v_eff, sub_dt, mask)

        self._diffusion_step(dt, DIFFUSIVITY_BASE, mask)
        self._decay_step(dt)

        # Record history
        spill_cells = np.sum(self.C > DETECTION_THRESHOLD) * DX * DY / 1e6  # km²
        self._history_area.append(float(round(spill_cells, 3)))
        self._history_mass.append(float(round(np.sum(self.C) * DX * DY, 1)))

    def apply_adsorption(self, row: int, col: int,
                         radius_cells: int, removed_kg_m2: float):
        """Remove oil concentration in a circular zone (hydrochar deployment)."""
        rr, cc = np.ogrid[:GRID_H, :GRID_W]
        dist = np.sqrt((rr - row)**2 + (cc - col)**2)
        mask = dist <= radius_cells
        removal = np.minimum(self.C, removed_kg_m2) * mask
        removed = float(np.sum(removal) * DX * DY)
        self.C -= removal
        self.C = np.maximum(self.C, 0.0)
        self.total_oil_removed_kg += removed
        return removed

    # ─────────────────────── Metrics ───────────────────────────────────────

    def get_metrics(self) -> dict:
        C = self.C
        sens = self.ocean.sensitivity
        spill_area_km2 = float(np.sum(C > DETECTION_THRESHOLD) * DX * DY / 1e6)
        total_mass_kg  = float(np.sum(C) * DX * DY)
        sensitivity_exposure = float(np.sum(C * sens) * DX * DY)
        max_conc = float(np.max(C))
        detected = bool(max_conc > DETECTION_THRESHOLD)
        return {
            "spill_area_km2": round(spill_area_km2, 3),
            "total_mass_kg":  round(total_mass_kg, 1),
            "max_concentration": round(max_conc, 4),
            "sensitivity_exposure": round(sensitivity_exposure, 1),
            "oil_removed_kg": round(self.total_oil_removed_kg, 1),
            "cleanup_efficiency_pct": round(
                100 * self.total_oil_removed_kg /
                max(self.total_oil_released_kg, 1e-3), 2),
            "detected": detected,
            "history_area":  self._history_area[-120:],
            "history_mass":  self._history_mass[-120:],
        }

    def get_concentration_grid(self) -> List[List[float]]:
        """Returns normalized concentration grid (0–1) for frontend heatmap."""
        normalized = np.clip(self.C / MAX_CONC, 0.0, 1.0)
        return normalized.tolist()
