"""
Ocean Environment Model — Bay of Bengal / Tamil Nadu Sea
=========================================================
SEA-FOCUSED redesign: the grid now represents the OCEAN surface east of
Tamil Nadu. The TN shoreline runs along the LEFT (west) edge of the grid.
The simulation domain is the Bay of Bengal open-sea surface.

Bounding box (sea side):
  LON 79.5° – 82.0° E   (west = TN coast, east = open Bay of Bengal)
  LAT  8.0° – 13.5° N   (south = Gulf of Mannar approach, north = Chennai)

Regions modelled:
  - Chennai Offshore       (12.5°–13.5°N) — shipping lane, high traffic
  - Coromandel Coast Shelf (11.0°–12.5°N) — important fishing ground
  - Palk Strait            ( 9.5°–11.0°N) — semi-enclosed, low energy
  - Gulf of Mannar Sea     ( 8.0°– 9.5°N) — coral/biodiversity-critical

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Tuple

from scipy.ndimage import gaussian_filter


# ─────────────────────────── Grid Configuration ────────────────────────────
GRID_W = 120          # Longitude cells  (~0.021° ≈ 2.3 km/cell)
GRID_H = 90           # Latitude  cells  (~0.061° ≈ 6.8 km/cell)
DX = 2_300.0          # metres per cell (x / longitude) — finer resolution
DY = 6_800.0          # metres per cell (y / latitude)

# ── Tamil Nadu SEA bounding box ─────────────────────────────────────────────
# West = TN coast (79.5°E), East = open Bay of Bengal (82.0°E)
LON_MIN, LON_MAX = 79.5, 82.0     # °E
LAT_MIN, LAT_MAX =  8.0, 13.5    # °N

# Fraction of grid width that is land (TN shoreline strip on the LEFT)
LAND_COLS = 6   # leftmost 6 columns = Tamil Nadu land (shoreline)


@dataclass
class OffshoreZone:
    name: str
    lon_range: Tuple[float, float]
    lat_range: Tuple[float, float]
    sensitivity: float       # 0 (low) → 1 (critical)
    current_speed_ms: float  # baseline current magnitude m/s
    zone_type: str           # "shipping" | "fishing" | "coral" | "strait"


OFFSHORE_ZONES: list[OffshoreZone] = [
    OffshoreZone("Chennai Offshore Shipping Lane",
                 (79.9, 82.0), (12.5, 13.5), 0.50, 0.45, "shipping"),
    OffshoreZone("Coromandel Shelf (Fishing Ground)",
                 (79.8, 81.5), (11.0, 12.5), 0.65, 0.30, "fishing"),
    OffshoreZone("Palk Strait (Semi-enclosed)",
                 (79.5, 80.8), ( 9.5, 11.0), 0.75, 0.12, "strait"),
    OffshoreZone("Gulf of Mannar Marine Reserve",
                 (79.5, 80.5), ( 8.0,  9.5), 0.98, 0.20, "coral"),
    OffshoreZone("Kaveri Delta Offshore",
                 (79.8, 80.8), (10.8, 11.5), 0.80, 0.22, "fishing"),
]

# Real Tamil Nadu port positions (lon, lat) for reference
TN_PORTS = {
    "Chennai":      (80.30, 13.08),
    "Ennore":       (80.33, 13.22),
    "Nagapattinam": (79.84, 10.77),
    "Tuticorin":    (78.19,  8.76),
    "Rameswaram":   (79.32,  9.28),
}


class OceanEnvironment:
    """
    Represents the Bay of Bengal sea surface east of Tamil Nadu.
    All grids are (GRID_H, GRID_W) arrays — row=latitude (N→S), col=longitude (W→E).

    Land mask:  1 = sea cell, 0 = land cell (TN coastline on left columns).
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.t   = 0.0           # simulation time (seconds)
        self.dt  = 300.0         # timestep in seconds (5 min per tick)

        # SAR satellite overpass: toggles every SAR_INTERVAL ticks
        self.sar_pass_active = False
        self._sar_interval   = 30    # ticks between SAR passes
        self._tick_count     = 0

        self._build_land_mask()
        self._build_sensitivity_grid()
        self._build_current_field()
        self._build_wind_field()

    # ─────────────────────── Coordinate helpers ─────────────────────────────

    def _lonlat_to_ij(self, lon: float, lat: float) -> Tuple[int, int]:
        col = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * (GRID_W - 1))
        row = int((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * (GRID_H - 1))
        return (np.clip(row, 0, GRID_H - 1), np.clip(col, 0, GRID_W - 1))

    # ─────────────────────── Land Mask ──────────────────────────────────────

    def _build_land_mask(self):
        """
        1 = sea cell, 0 = land cell.
        TN coastline = LEFT (west) columns. The rest is Bay of Bengal.
        Irregular shoreline: estuaries, deltas, creek openings.
        """
        mask = np.ones((GRID_H, GRID_W), dtype=np.float32)

        # Base land strip: leftmost LAND_COLS columns = TN coast
        mask[:, :LAND_COLS] = 0.0

        # Irregular shoreline detail (estuaries break into sea)
        # Kaveri delta mouth (lat ~10.8–11.0N → rows ~37–40)
        for row in [37, 38, 39, 40]:
            mask[row, :LAND_COLS + 3] = 0.0
            mask[row, LAND_COLS - 1]  = 1.0   # river mouth channel

        # Vedaranyam / Point Calimere (lat ~10.3N → row ~47)
        for row in [46, 47, 48]:
            mask[row, :LAND_COLS + 2] = 0.0
            mask[row, LAND_COLS]      = 1.0

        # Palk Strait narrowing: Mandapam/Rameswaram region (lat ~9.2–9.5N → rows ~60–65)
        for row in range(60, 66):
            mask[row, :LAND_COLS + 5] = 0.0   # wider land (Indian peninsula)
            # Leave channel for Palk Strait current
            mask[row, LAND_COLS + 3]  = 1.0
            mask[row, LAND_COLS + 4]  = 1.0

        self.land_mask = mask

    # ─────────────────────── Sensitivity Grid ───────────────────────────────

    def _build_sensitivity_grid(self):
        """
        Ecological sensitivity 0→1 for offshore zones.
        Gulf of Mannar coral reef = critical (0.98).
        Shipping lanes = moderate.
        """
        sens = np.full((GRID_H, GRID_W), 0.25, dtype=np.float32)
        for zone in OFFSHORE_ZONES:
            r0, c0 = self._lonlat_to_ij(zone.lon_range[0], zone.lat_range[0])
            r1, c1 = self._lonlat_to_ij(zone.lon_range[1], zone.lat_range[1])
            r0, r1 = min(r0, r1), max(r0, r1)
            c0, c1 = min(c0, c1), max(c0, c1)
            sens[r0:r1+1, c0:c1+1] = np.maximum(
                sens[r0:r1+1, c0:c1+1], zone.sensitivity
            )
        # Only sea cells have ecological significance
        self.sensitivity = sens * self.land_mask

    # ─────────────────────── Current Field ──────────────────────────────────

    def _build_current_field(self):
        """
        Bay of Bengal surface current field:
        - NE monsoon (Oct–Jan): southward along coast, u≈−0.2 m/s
        - Bay of Bengal gyre (anti-clockwise)
        - Tidal oscillation (M2 constituent)
        - Eddy perturbations
        """
        x = np.linspace(0, 2 * np.pi, GRID_W)
        y = np.linspace(0, 2 * np.pi, GRID_H)
        XX, YY = np.meshgrid(x, y)

        # Bay of Bengal NE monsoon surface current
        # Broadly southward along coast (−v) and slightly eastward offshore
        self.u_base = (0.10 * np.sin(YY * 0.7) + 0.20 * np.cos(XX * 0.5)).astype(np.float32)
        self.v_base = (-0.22 * np.ones((GRID_H, GRID_W)) +
                       0.08 * np.sin(XX)).astype(np.float32)

        # Palk Strait: restrict flow (low energy)
        r_palk0, _ = self._lonlat_to_ij(79.5,  9.5)
        r_palk1, _ = self._lonlat_to_ij(79.5, 11.0)
        rlo, rhi = min(r_palk0, r_palk1), max(r_palk0, r_palk1)
        self.u_base[rlo:rhi, :30] *= 0.25
        self.v_base[rlo:rhi, :30] *= 0.25

        # Eddy field (smoothed random)
        nu = self.rng.standard_normal((GRID_H, GRID_W)).astype(np.float32)
        nv = self.rng.standard_normal((GRID_H, GRID_W)).astype(np.float32)
        self.eddy_u = gaussian_filter(nu * 0.06, sigma=6)
        self.eddy_v = gaussian_filter(nv * 0.06, sigma=6)

        # Tidal amplitude (stronger in Palk Strait and Gulf of Mannar)
        self.tidal_amp = np.ones((GRID_H, GRID_W), dtype=np.float32) * 0.10
        self.tidal_amp[rlo:rhi, :40] = 0.30   # Palk Strait tidal amplification

    # ─────────────────────── Wind Field ─────────────────────────────────────

    def _build_wind_field(self):
        """
        Bay of Bengal NE monsoon wind (Oct–Feb dominant pattern).
        Beaufort 4–5 NE wind (45°), veering to SE in SW monsoon.
        """
        self.wind_speed_ms  = 7.5                     # m/s (Beaufort 4–5)
        self.wind_dir_rad   = np.deg2rad(45.0)        # NE → blows toward SW
        self.wind_drag_coeff = 0.013

    # ─────────────────────── Public Step ────────────────────────────────────

    def step(self):
        """Advance environment one timestep."""
        self.t += self.dt
        self._tick_count += 1

        # Stochastic wind gusts
        self.wind_speed_ms = float(np.clip(
            self.wind_speed_ms + self.rng.normal(0, 0.4), 2.0, 22.0
        ))
        self.wind_dir_rad += self.rng.normal(0, 0.015)

        # Toggle SAR pass
        if self._tick_count % self._sar_interval == 0:
            self.sar_pass_active = True
        elif self._tick_count % self._sar_interval == 3:
            self.sar_pass_active = False   # pass lasts 3 ticks

    def get_current_field(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (u, v) current velocity arrays (m/s) including tidal component."""
        omega_m2 = 2 * np.pi / (12.42 * 3600)   # M2 tidal frequency
        tidal    = self.tidal_amp * np.sin(omega_m2 * self.t)
        u = (self.u_base + self.eddy_u + tidal)     * self.land_mask
        v = (self.v_base + self.eddy_v + tidal * 0.5) * self.land_mask
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
            "t":             self.t,
            "wind_speed":    round(self.wind_speed_ms, 2),
            "wind_dir_deg":  round(float(np.rad2deg(self.wind_dir_rad) % 360), 1),
            "sar_pass":      self.sar_pass_active,
            "current_u":     u.tolist(),
            "current_v":     v.tolist(),
            "sensitivity":   self.sensitivity.tolist(),
            "land_mask":     self.land_mask.tolist(),
        }
