"""
Ocean Environment Model
=======================
Simulates heterogeneous Tamil Nadu coastal regions with spatially varying
ocean currents, wind forcing, and ecological sensitivity grids.

Regions modelled:
  - Coromandel Coast  (open coast, high-energy)
  - Palk Bay          (semi-enclosed, low-energy)
  - Gulf of Mannar    (biodiversity-rich, coral reefs)
  - Mangroves/Estuaries (high sensitivity)

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Tuple


# ─────────────────────────── Grid Configuration ────────────────────────────
GRID_W = 120          # Longitude cells  (~0.05° resolution ≈ 5.5 km/cell)
GRID_H = 90           # Latitude  cells
DX = 5_500.0          # metres per cell (x)
DY = 5_500.0          # metres per cell (y)

# Tamil Nadu lat/lon bounding box (approximate simulation extent)
LON_MIN, LON_MAX = 78.0, 80.0    # °E
LAT_MIN, LAT_MAX = 8.0, 13.5    # °N


@dataclass
class CoastalZone:
    name: str
    lon_range: Tuple[float, float]
    lat_range: Tuple[float, float]
    sensitivity: float          # 0 (low) → 1 (critical)
    current_speed_ms: float     # baseline current magnitude m/s
    color_hint: str             # for frontend rendering


COASTAL_ZONES: list[CoastalZone] = [
    CoastalZone("Coromandel Coast",   (79.5, 80.2), (11.0, 13.5), 0.55, 0.35, "#1a6fa8"),
    CoastalZone("Palk Bay",           (79.0, 80.0), (9.5,  11.0), 0.70, 0.15, "#2e9e6b"),
    CoastalZone("Gulf of Mannar",     (78.0, 79.5), (8.0,   9.5), 0.95, 0.25, "#e8a020"),
    CoastalZone("Mangroves/Estuaries",(79.8, 80.2), (10.5, 11.5), 1.00, 0.08, "#6d4c41"),
]


class OceanEnvironment:
    """
    Holds the spatially varying current field, wind field, land mask,
    shoreline mask, and ecological sensitivity grid.

    All grids are (GRID_H, GRID_W) shaped arrays, using (row=lat, col=lon)
    indexing consistent with geographic convention.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.t = 0.0          # simulation time (seconds)
        self.dt = 300.0       # timestep in seconds (5 min per tick)

        self._build_land_mask()
        self._build_sensitivity_grid()
        self._build_current_field()
        self._build_wind_field()

    # ─────────────────────── Internal Builders ─────────────────────────────

    def _lonlat_to_ij(self, lon: float, lat: float) -> Tuple[int, int]:
        col = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * (GRID_W - 1))
        row = int((lat - LAT_MIN) / (LAT_MAX - LAT_MIN) * (GRID_H - 1))
        return (np.clip(row, 0, GRID_H - 1), np.clip(col, 0, GRID_W - 1))

    def _build_land_mask(self):
        """
        1 = ocean cell, 0 = land cell.
        Approximates the Tamil Nadu shoreline shape with a simple parametric
        boundary (right edge of the grid = shoreline, left portion = ocean).
        """
        self.land_mask = np.ones((GRID_H, GRID_W), dtype=np.float32)
        # Simplified: rightmost 8 columns = land (shoreline)
        self.land_mask[:, GRID_W - 8:] = 0.0
        # Add narrow estuary channels (land breaks) for realism
        for row in [20, 35, 55, 70]:
            self.land_mask[row, GRID_W - 12: GRID_W - 6] = 1.0

    def _build_sensitivity_grid(self):
        """
        Ecological sensitivity 0→1 based on coastal zone polygons.
        Decays inversely with distance from high-sensitivity zones.
        """
        self.sensitivity = np.full((GRID_H, GRID_W), 0.3, dtype=np.float32)
        for zone in COASTAL_ZONES:
            r0, c0 = self._lonlat_to_ij(zone.lon_range[0], zone.lat_range[0])
            r1, c1 = self._lonlat_to_ij(zone.lon_range[1], zone.lat_range[1])
            r0, r1 = sorted([r0, r1])
            c0, c1 = sorted([c0, c1])
            self.sensitivity[r0:r1+1, c0:c1+1] = np.maximum(
                self.sensitivity[r0:r1+1, c0:c1+1], zone.sensitivity
            )
        self.sensitivity *= self.land_mask   # zero sensitivity on land

    def _build_current_field(self):
        """
        Spatially varying current velocity field (u=east, v=north) in m/s.
        Composed of:
          - Geostrophic background flow
          - Tidal oscillation (M2 tidal constituent approximation)
          - Eddy perturbations (smoothed Gaussian random field)
        """
        x = np.linspace(0, 2 * np.pi, GRID_W)
        y = np.linspace(0, 2 * np.pi, GRID_H)
        XX, YY = np.meshgrid(x, y)

        # Geostrophic base flow (NE monsoon pattern)
        self.u_base = (0.25 * np.sin(YY) + 0.10 * np.cos(XX)).astype(np.float32)
        self.v_base = (0.15 * np.cos(YY) - 0.08 * np.sin(XX * 0.5)).astype(np.float32)

        # Eddy field (smoothed random)
        noise_u = self.rng.standard_normal((GRID_H, GRID_W)).astype(np.float32)
        noise_v = self.rng.standard_normal((GRID_H, GRID_W)).astype(np.float32)
        from scipy.ndimage import gaussian_filter
        self.eddy_u = gaussian_filter(noise_u * 0.05, sigma=5)
        self.eddy_v = gaussian_filter(noise_v * 0.05, sigma=5)

        # Tidal amplitude grid (stronger in Palk Bay)
        self.tidal_amp = np.ones((GRID_H, GRID_W), dtype=np.float32) * 0.12
        r0, c0 = self._lonlat_to_ij(79.0, 9.5)
        r1, c1 = self._lonlat_to_ij(80.0, 11.0)
        self.tidal_amp[min(r0,r1):max(r0,r1), min(c0,c1):max(c0,c1)] = 0.28

    def _build_wind_field(self):
        """
        Seasonal NE monsoon wind field with stochastic gusts.
        Wind stress drives surface current correction τ = ρ_a * C_d * W²
        """
        self.wind_speed_ms = 6.0          # m/s baseline (Beaufort 4)
        self.wind_dir_rad  = np.deg2rad(45.0)  # NE direction
        self.wind_drag_coeff = 0.015      # surface drag coefficient

    # ─────────────────────── Public Interface ──────────────────────────────

    def step(self):
        """Advance environment one timestep."""
        self.t += self.dt
        # Update wind gusts
        self.wind_speed_ms = max(2.0, self.wind_speed_ms +
                                 self.rng.normal(0, 0.3))
        self.wind_speed_ms = min(self.wind_speed_ms, 18.0)
        # Vary wind direction slowly
        self.wind_dir_rad += self.rng.normal(0, 0.02)

    def get_current_field(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns (u, v) current velocity arrays (m/s) at current time,
        including tidal oscillation.
        """
        omega_m2 = 2 * np.pi / (12.42 * 3600)   # M2 tidal frequency
        tidal = self.tidal_amp * np.sin(omega_m2 * self.t)
        u = (self.u_base + self.eddy_u + tidal) * self.land_mask
        v = (self.v_base + self.eddy_v + tidal * 0.6) * self.land_mask
        return u.astype(np.float32), v.astype(np.float32)

    def get_wind_forcing(self) -> Tuple[float, float]:
        """Returns (wu, wv) wind velocity components (m/s)."""
        wu = self.wind_speed_ms * np.cos(self.wind_dir_rad)
        wv = self.wind_speed_ms * np.sin(self.wind_dir_rad)
        return float(wu), float(wv)

    def get_state_dict(self) -> dict:
        u, v = self.get_current_field()
        wu, wv = self.get_wind_forcing()
        return {
            "t": self.t,
            "wind_speed": round(self.wind_speed_ms, 2),
            "wind_dir_deg": round(np.rad2deg(self.wind_dir_rad) % 360, 1),
            "current_u": u.tolist(),
            "current_v": v.tolist(),
            "sensitivity": self.sensitivity.tolist(),
            "land_mask": self.land_mask.tolist(),
        }
