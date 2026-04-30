"""
Magnetic Hydrochar Adsorption Module
=====================================
Simulates oil removal using carbon-based magnetic hydrochar adsorbents
deployed in coastal spill zones.

Mathematical Model:
-------------------
Adsorption follows Langmuir isotherm (equilibrium):

    q_e = (q_max · K_L · C_e) / (1 + K_L · C_e)

Where:
    q_e    – equilibrium adsorption capacity (mg_oil / g_adsorbent)
    q_max  – maximum monolayer capacity (mg/g) — calibrated to ~1200 mg/g
              for magnetic biochar derived from rice husk (Tamil Nadu sourced)
    K_L    – Langmuir constant (L/mg)
    C_e    – equilibrium oil concentration (mg/L)

Time-dependent adsorption (pseudo-second-order kinetics):

    dq/dt = k2 · (q_e - q(t))²

Integrated:
    q(t) = q_e² · k2 · t / (1 + q_e · k2 · t)

Oil concentration reduction per deployment zone:
    ΔC = q(t) · ρ_ads / (DX · DY)     [kg/m²]

Magnetic separation & reuse:
    - Adsorbent recovered by permanent magnet array (simulated as 95% recovery)
    - Each reuse cycle degrades capacity: q_max_n = q_max · (1 - 0.05)^n
    - Max reuse cycles = 10 before disposal

Reference Parameters (calibrated to literature):
    q_max = 1200 mg/g   (Yao et al., 2020 — magnetic biochar)
    K_L   = 0.042 L/mg
    k2    = 3.5×10⁻⁴ g/(mg·s)
    ρ_ads deployment density = 0.5 kg/m² per zone

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from .ocean_model import GRID_H, GRID_W, DX, DY


# ─────────────────────────── Adsorption Constants ───────────────────────────
Q_MAX_MG_G          = 1200.0         # mg oil per g adsorbent (Langmuir max)
K_L_L_MG            = 0.042          # L/mg (Langmuir constant)
K2_G_MG_S           = 3.5e-4         # g/(mg·s) pseudo-second-order rate
DENSITY_ADS_KG_M2   = 0.5            # deployment density kg/m²
RECOVERY_EFFICIENCY = 0.95           # magnetic separation recovery
EFFICIENCY_DECAY    = 0.05           # capacity loss per reuse cycle
MAX_REUSE_CYCLES    = 10
DEPLOYMENT_RADIUS   = 8              # cells


@dataclass
class HydrocharUnit:
    unit_id: int
    row: int
    col: int
    mass_kg: float                    # deployed mass
    reuse_count: int = 0
    t_deployed: float = 0.0
    active: bool = True
    oil_adsorbed_mg_g: float = 0.0   # cumulative adsorption (mg/g)
    total_oil_removed_kg: float = 0.0

    @property
    def current_q_max(self) -> float:
        """Degraded capacity after multiple reuse cycles."""
        return Q_MAX_MG_G * ((1 - EFFICIENCY_DECAY) ** self.reuse_count)

    @property
    def efficiency_pct(self) -> float:
        return 100.0 * (1 - EFFICIENCY_DECAY) ** self.reuse_count


class HydrocharModule:
    """
    Manages the lifecycle of magnetic hydrochar adsorbent units:
    deployment, adsorption kinetics, magnetic recovery, and reuse.
    """

    def __init__(self):
        self.units: List[HydrocharUnit] = []
        self.total_available_mass_kg  = 1000.0   # stockpile
        self.total_deployed_mass_kg   = 0.0
        self.total_removed_oil_kg     = 0.0
        self._unit_counter            = 0
        self._history_removed: List[float] = []
        self._history_efficiency: List[float] = []

    # ─────────────────────── Deployment ────────────────────────────────────

    def deploy(self, row: int, col: int, mass_kg: float = 50.0,
               t_current: float = 0.0) -> Optional[HydrocharUnit]:
        """Deploy a hydrochar unit at a given grid cell."""
        if mass_kg > self.total_available_mass_kg:
            mass_kg = self.total_available_mass_kg
        if mass_kg <= 0:
            return None

        unit = HydrocharUnit(
            unit_id=self._unit_counter,
            row=row, col=col,
            mass_kg=mass_kg,
            t_deployed=t_current,
        )
        self.units.append(unit)
        self.total_available_mass_kg -= mass_kg
        self.total_deployed_mass_kg  += mass_kg
        self._unit_counter += 1
        return unit

    # ─────────────────────── Langmuir Isotherm ─────────────────────────────

    @staticmethod
    def langmuir_q_e(C_e_mg_L: float, q_max: float) -> float:
        """
        Equilibrium adsorption capacity from Langmuir isotherm.
        C_e in mg/L → q_e in mg/g
        """
        return (q_max * K_L_L_MG * C_e_mg_L) / (1 + K_L_L_MG * C_e_mg_L)

    @staticmethod
    def pseudo_second_order_q(q_e: float, k2: float, t_s: float) -> float:
        """
        Pseudo-second-order integrated rate equation.
        Returns q(t) in mg/g after time t_s seconds.
        """
        denom = 1 + q_e * k2 * t_s
        return (q_e**2 * k2 * t_s) / max(denom, 1e-12)

    # ─────────────────────── Adsorption Step ───────────────────────────────

    def step(self, concentration_grid: np.ndarray,
             oil_engine, t_current: float) -> None:
        """
        For each active hydrochar unit, compute oil removed this timestep
        and apply it to the concentration grid via oil_engine.
        """
        total_removed_this_step = 0.0

        for unit in self.units:
            if not unit.active:
                continue

            # Oil concentration at unit cell (convert kg/m² → mg/L)
            ri, ci = int(np.clip(unit.row, 0, GRID_H - 1)), \
                     int(np.clip(unit.col, 0, GRID_W - 1))
            C_kg_m2 = float(concentration_grid[ri, ci])

            # Convert kg/m² to mg/L (assume 1 mm surface film depth = 0.001 m)
            C_mg_L  = C_kg_m2 * 1e3 / (880.0 * 0.001)   # density of oil

            if C_mg_L < 0.1:
                continue  # negligible oil

            # Langmuir equilibrium capacity
            q_e = self.langmuir_q_e(C_mg_L, unit.current_q_max)

            # Time elapsed since deployment
            t_elapsed = t_current - unit.t_deployed
            q_t = self.pseudo_second_order_q(q_e, K2_G_MG_S, t_elapsed)

            # Additional adsorption this tick (Δq)
            dt_s = 300.0  # simulation timestep seconds
            q_prev = self.pseudo_second_order_q(q_e, K2_G_MG_S,
                                                max(t_elapsed - dt_s, 0))
            delta_q_mg_g = max(q_t - q_prev, 0.0)

            # Mass of oil removed: delta_q [mg/g] × mass [g] → mg → kg
            mass_g = unit.mass_kg * 1000.0
            oil_removed_mg = delta_q_mg_g * mass_g
            oil_removed_kg = oil_removed_mg * 1e-6

            # Apply removal to grid
            radius = DEPLOYMENT_RADIUS
            actual_removed = oil_engine.apply_adsorption(
                ri, ci, radius,
                removed_kg_m2=oil_removed_kg / (np.pi * (radius * DX)**2)
            )

            unit.oil_adsorbed_mg_g  += delta_q_mg_g
            unit.total_oil_removed_kg += actual_removed
            total_removed_this_step   += actual_removed

            # Check saturation (90% of max capacity)
            if unit.oil_adsorbed_mg_g >= 0.9 * unit.current_q_max:
                self._recover_unit(unit, t_current)

        self.total_removed_oil_kg += total_removed_this_step
        self._history_removed.append(round(self.total_removed_oil_kg, 1))
        avg_eff = np.mean([u.efficiency_pct for u in self.units]) \
                  if self.units else 100.0
        self._history_efficiency.append(round(float(avg_eff), 1))

    # ─────────────────────── Magnetic Recovery & Reuse ─────────────────────

    def _recover_unit(self, unit: HydrocharUnit, t_current: float):
        """Simulate magnetic separation and re-add to stockpile."""
        recovered_mass = unit.mass_kg * RECOVERY_EFFICIENCY
        unit.reuse_count += 1
        unit.oil_adsorbed_mg_g = 0.0
        unit.t_deployed = t_current

        if unit.reuse_count >= MAX_REUSE_CYCLES:
            unit.active = False
            # Dispose — mass lost from system
        else:
            # Reset for reuse (in-place, redeployed at same location)
            self.total_available_mass_kg += (unit.mass_kg - recovered_mass)
            unit.mass_kg = recovered_mass

    # ─────────────────────── Metrics ───────────────────────────────────────

    def get_metrics(self) -> dict:
        active_units = [u for u in self.units if u.active]
        avg_efficiency = (np.mean([u.efficiency_pct for u in self.units])
                          if self.units else 100.0)
        avg_reuse = (np.mean([u.reuse_count for u in self.units])
                     if self.units else 0.0)
        return {
            "total_units_deployed": len(self.units),
            "active_units":         len(active_units),
            "total_available_kg":   round(self.total_available_mass_kg, 1),
            "total_deployed_kg":    round(self.total_deployed_mass_kg, 1),
            "total_removed_oil_kg": round(self.total_removed_oil_kg, 1),
            "avg_efficiency_pct":   round(float(avg_efficiency), 1),
            "avg_reuse_count":      round(float(avg_reuse), 1),
            "history_removed":      self._history_removed[-120:],
            "history_efficiency":   self._history_efficiency[-120:],
        }

    def get_units_list(self) -> list:
        return [
            {
                "id":              u.unit_id,
                "row":             u.row,
                "col":             u.col,
                "mass_kg":         round(u.mass_kg, 1),
                "reuse_count":     u.reuse_count,
                "efficiency_pct":  round(u.efficiency_pct, 1),
                "oil_adsorbed":    round(u.oil_adsorbed_mg_g, 2),
                "total_removed_kg": round(u.total_oil_removed_kg, 3),
                "active":          u.active,
                "radius":          DEPLOYMENT_RADIUS,
            }
            for u in self.units
        ]
