"""
Oil Spill Simulation Engine — Bay of Bengal Sea Surface
=========================================================
Implements 2D Advection-Diffusion-Decay PDE for oil concentration on
the sea surface:

    ∂C/∂t = D∇²C  -  u·∇C  -  λC  +  S(x,y,t)

Additional sea-surface physics:
  - SAR detection model: oil suppresses capillary wave roughness
    → detectable as dark patches in radar backscatter
  - Oil slick typing: thin sheen (<0.3 μm) vs thick mousse (>1 mm)
  - Emulsification: water-in-oil increases volume by factor ~3-4

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from .ocean_model import OceanEnvironment, GRID_W, GRID_H, DX, DY


# ─────────────────────────── Physical Constants ─────────────────────────────
DIFFUSIVITY_BASE    = 3.5        # m²/s  (open ocean turbulent diffusivity)
DECAY_RATE          = 2.0e-6     # 1/s   ≈ 17% evaporation/day (crude oil)
WIND_DRIFT_FACTOR   = 0.035      # 3.5% of wind speed drives surface oil
DENSITY_OIL         = 880.0      # kg/m³ (medium crude)
MAX_CONC            = 50.0       # kg/m² (display clamping)

# Detection thresholds
SENSOR_DETECTION_THRESHOLD = 0.05    # kg/m² — buoy in-situ sensor
SAR_DETECTION_THRESHOLD    = 0.0015  # kg/m² — SAR is very sensitive to thin films
DRONE_DETECTION_THRESHOLD  = 0.01    # kg/m² — aerial visual detection

# Oil film thickness → slick type classification (kg/m² → mm thickness)
# thickness [mm] = concentration [kg/m²] / (density [kg/m³] / 1000)
SHEEN_MAX_CONC   = 0.50   # < 0.5 kg/m² → rainbow sheen (iridescent)
MOUSSE_MIN_CONC  = 5.0    # > 5.0 kg/m² → water-in-oil mousse (brown)


def classify_slick(conc_kg_m2: float) -> str:
    if conc_kg_m2 < SHEEN_MAX_CONC:
        return "sheen"
    elif conc_kg_m2 < MOUSSE_MIN_CONC:
        return "slick"
    else:
        return "mousse"


@dataclass
class SpillEvent:
    row: int
    col: int
    total_mass_kg: float
    release_rate_kg_s: float
    t_start: float
    t_end: Optional[float] = None
    active: bool = True
    label: str = "SPILL"


class OilSpillEngine:
    """
    Manages oil concentration grid on the Bay of Bengal sea surface.
    Supports SAR satellite detection simulation and slick classification.
    """

    def __init__(self, ocean: OceanEnvironment):
        self.ocean = ocean
        self.C = np.zeros((GRID_H, GRID_W), dtype=np.float64)
        self.spills: List[SpillEvent] = []
        self.total_oil_released_kg  = 0.0
        self.total_oil_removed_kg   = 0.0
        self._history_area: List[float] = []
        self._history_mass: List[float] = []

        # SAR detection state
        self.sar_detected       = False
        self.sar_slick_cells    = 0
        self.sar_slick_area_km2 = 0.0

    # ─────────────────────── Spill Management ──────────────────────────────

    def add_spill(self, row: int, col: int,
                  total_mass_kg: float = 5000.0,
                  release_rate_kg_s: float = 0.5,
                  label: str = "SPILL") -> SpillEvent:
        # Ensure spill is in sea (land_mask=1)
        r = int(np.clip(row, 0, GRID_H - 1))
        c = int(np.clip(col, 0, GRID_W - 1))
        if self.ocean.land_mask[r, c] < 0.5:
            # Move spill offshore (find nearest sea cell)
            c = max(c + 8, 8)
        ev = SpillEvent(
            row=r, col=c,
            total_mass_kg=total_mass_kg,
            release_rate_kg_s=release_rate_kg_s,
            t_start=self.ocean.t,
            label=label,
        )
        self.spills.append(ev)
        return ev

    def _apply_sources(self, dt: float):
        for spill in self.spills:
            if not spill.active:
                continue
            if self.total_oil_released_kg >= spill.total_mass_kg:
                spill.active = False
                continue
            injected = spill.release_rate_kg_s * dt / (DX * DY)
            self.C[spill.row, spill.col] += injected
            self.total_oil_released_kg   += injected * DX * DY

    # ─────────────────────── PDE Operators ─────────────────────────────────

    def _diffusion_step(self, dt: float, D: float, mask: np.ndarray):
        C   = self.C
        lap = (
            np.roll(C, -1, axis=1) + np.roll(C, 1, axis=1) - 2 * C
        ) / DX**2 + (
            np.roll(C, -1, axis=0) + np.roll(C, 1, axis=0) - 2 * C
        ) / DY**2
        self.C = np.maximum(0.0, (C + D * lap * dt) * mask)

    def _advection_step(self, u: np.ndarray, v: np.ndarray,
                        dt: float, mask: np.ndarray):
        C  = self.C.copy()
        dC = np.zeros_like(C)
        u_pos = np.maximum(u, 0);  u_neg = np.minimum(u, 0)
        v_pos = np.maximum(v, 0);  v_neg = np.minimum(v, 0)

        dC -= (u_pos * (C - np.roll(C, 1, axis=1)) / DX +
               u_neg * (np.roll(C, -1, axis=1) - C) / DX) * dt
        dC -= (v_pos * (C - np.roll(C, 1, axis=0)) / DY +
               v_neg * (np.roll(C, -1, axis=0) - C) / DY) * dt

        self.C = np.maximum(0.0, (C + dC) * mask)

    def _decay_step(self, dt: float):
        self.C *= np.exp(-DECAY_RATE * dt)

    # ─────────────────────── SAR Simulation ─────────────────────────────────

    def update_sar_detection(self):
        """
        Simulate SAR satellite detection.
        Oil suppresses sea-surface capillary waves → lower radar backscatter.
        Detectable at much lower concentration than point sensors.
        """
        if self.ocean.sar_pass_active:
            sar_mask = self.C > SAR_DETECTION_THRESHOLD
            self.sar_slick_cells    = int(np.sum(sar_mask))
            self.sar_slick_area_km2 = float(self.sar_slick_cells * DX * DY / 1e6)
            self.sar_detected       = self.sar_slick_cells > 0
        else:
            # Retain last detection result between passes
            pass

    def get_sar_slick_map(self) -> list:
        """Returns binary grid of SAR-detectable oil cells for frontend."""
        if not self.ocean.sar_pass_active:
            return []
        sar_grid = (self.C > SAR_DETECTION_THRESHOLD).astype(np.float32)
        return sar_grid.tolist()

    # ─────────────────────── Main Step ─────────────────────────────────────

    def step(self) -> None:
        dt   = self.ocean.dt
        mask = self.ocean.land_mask.astype(np.float64)

        self._apply_sources(dt)

        u, v   = self.ocean.get_current_field()
        wu, wv = self.ocean.get_wind_forcing()

        u_eff = u.astype(np.float64) + WIND_DRIFT_FACTOR * wu
        v_eff = v.astype(np.float64) + WIND_DRIFT_FACTOR * wv

        # CFL sub-stepping
        max_vel = max(np.max(np.abs(u_eff)), np.max(np.abs(v_eff)), 1e-6)
        cfl_dt  = 0.9 * min(DX, DY) / max_vel
        n_sub   = max(1, int(np.ceil(dt / cfl_dt)))
        sub_dt  = dt / n_sub

        for _ in range(n_sub):
            self._advection_step(u_eff, v_eff, sub_dt, mask)

        self._diffusion_step(dt, DIFFUSIVITY_BASE, mask)
        self._decay_step(dt)
        self.update_sar_detection()

        # Track history
        spill_area = float(np.sum(self.C > SENSOR_DETECTION_THRESHOLD) * DX * DY / 1e6)
        self._history_area.append(round(spill_area, 3))
        self._history_mass.append(round(float(np.sum(self.C) * DX * DY), 1))

    def apply_adsorption(self, row: int, col: int,
                         radius_cells: int, removed_kg_m2: float) -> float:
        rr, cc = np.ogrid[:GRID_H, :GRID_W]
        dist   = np.sqrt((rr - row)**2 + (cc - col)**2)
        mask   = dist <= radius_cells
        removal = np.minimum(self.C, removed_kg_m2) * mask
        removed = float(np.sum(removal) * DX * DY)
        self.C  -= removal
        self.C   = np.maximum(self.C, 0.0)
        self.total_oil_removed_kg += removed
        return removed

    # ─────────────────────── Metrics ───────────────────────────────────────

    def get_metrics(self) -> dict:
        C = self.C
        sens = self.ocean.sensitivity
        spill_area_km2       = float(np.sum(C > SENSOR_DETECTION_THRESHOLD) * DX * DY / 1e6)
        total_mass_kg        = float(np.sum(C) * DX * DY)
        sensitivity_exposure = float(np.sum(C * sens) * DX * DY)
        max_conc             = float(np.max(C))
        dominant_type        = classify_slick(max_conc) if max_conc > 0 else "none"

        return {
            "spill_area_km2":        round(spill_area_km2, 3),
            "total_mass_kg":         round(total_mass_kg, 1),
            "max_concentration":     round(max_conc, 4),
            "sensitivity_exposure":  round(sensitivity_exposure, 1),
            "oil_removed_kg":        round(self.total_oil_removed_kg, 1),
            "cleanup_efficiency_pct": round(
                100 * self.total_oil_removed_kg /
                max(self.total_oil_released_kg, 1e-3), 2),
            "detected":              bool(max_conc > SENSOR_DETECTION_THRESHOLD),
            "sar_detected":          self.sar_detected,
            "sar_slick_area_km2":    round(self.sar_slick_area_km2, 2),
            "slick_type":            dominant_type,
            "history_area":          self._history_area[-120:],
            "history_mass":          self._history_mass[-120:],
        }

    def get_concentration_grid(self) -> list:
        """Normalized concentration grid (0–1) for frontend heatmap."""
        return np.clip(self.C / MAX_CONC, 0.0, 1.0).tolist()
