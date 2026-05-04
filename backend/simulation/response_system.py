"""
Indian Coast Guard Response System — Bay of Bengal
====================================================
Simulates real-world multi-agency maritime response to sea oil spills.

Vessels dispatched from real Tamil Nadu ICG stations:
  - ICGS Chennai     (13.08°N, 80.30°E) — Fast Patrol Vessel, 25 kn
  - ICGS Tuticorin   ( 8.76°N, 78.19°E) — Pollution Control Vessel, 15 kn
  - ICGS Rameswaram  ( 9.28°N, 79.32°E) — Interceptor Boat, 40 kn
  - ICG Aerial Helo  (13.08°N, 80.30°E) — Chetak helicopter, 180 km/h

Response workflow:
  1. Detection by WSN buoy OR SAR satellite → ALERT
  2. ICG coordination centre notified
  3. Nearest vessel dispatched (proximity-based, not fixed delay)
  4. Aerial helo dispatched for visual confirmation
  5. Vessels apply oil skimming + dispersant spraying on arrival

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import List, Optional
from .ocean_model import (OceanEnvironment, GRID_H, GRID_W, DX, DY,
                          LON_MIN, LON_MAX, LAT_MIN, LAT_MAX, LAND_COLS)
from .oil_spill_engine import OilSpillEngine, SENSOR_DETECTION_THRESHOLD


def _lonlat_to_rc(lon: float, lat: float):
    col = float(np.clip((lon - LON_MIN) / (LON_MAX - LON_MIN) * GRID_W, 0, GRID_W - 1))
    row = float(np.clip((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * GRID_H, 0, GRID_H - 1))
    return row, col


# ─────────────────────────── ICG Station Registry ────────────────────────────
ICG_STATIONS = [
    {
        "name":        "ICGS Chennai FPV",
        "lon":          80.30, "lat": 13.08,
        "type":         "fast_patrol",
        "speed_kn":     25.0,
        "delay_s":      1800,   # 30 min mobilisation
        "skim_rate":    0.35,   # kg/s mechanical skimming
        "skim_radius":  8,
    },
    {
        "name":        "ICGS Tuticorin PCV",
        "lon":          78.19, "lat":  8.76,
        "type":         "pollution_control",
        "speed_kn":     15.0,
        "delay_s":      3600,   # 1 h mobilisation
        "skim_rate":    0.80,   # oil recovery vessel — higher rate
        "skim_radius":  12,
    },
    {
        "name":        "ICGS Rameswaram IB",
        "lon":          79.32, "lat":  9.28,
        "type":         "interceptor",
        "speed_kn":     40.0,
        "delay_s":      900,    # 15 min
        "skim_rate":    0.15,
        "skim_radius":  5,
    },
    {
        "name":        "ICG Chetak Helicopter",
        "lon":          80.30, "lat": 13.08,
        "type":         "aerial",
        "speed_kn":     95.0,   # ~180 km/h
        "delay_s":      600,    # 10 min scramble
        "skim_rate":    0.0,    # aerial: surveillance/dispersant only
        "skim_radius":  0,
    },
]

KNOTS_TO_MS = 0.5144


@dataclass
class Alert:
    alert_id:         int
    t_generated:      float
    spill_row:        int
    spill_col:        int
    max_concentration:float
    detection_source: str   # "WSN_BUOY" | "SAR_SATELLITE" | "AERIAL_DRONE"
    node_id_detected: Optional[int] = None
    acknowledged:     bool = False


@dataclass
class CoastGuardVessel:
    vessel_id:    int
    name:         str
    vessel_type:  str
    row:          float
    col:          float
    home_row:     float
    home_col:     float
    target_row:   float
    target_col:   float
    t_mobilized:  float
    speed_ms:     float
    skim_rate:    float
    skim_radius:  int
    active:       bool  = False
    on_site:      bool  = False
    oil_removed_kg: float = 0.0
    status:       str   = "standby"

    @property
    def speed_cells_s(self) -> float:
        # Use average of DX, DY for simplicity
        return self.speed_ms / ((DX + DY) / 2)


class ResponseSystem:
    """
    Manages oil spill detection, ICG vessel dispatch, and cleanup operations.
    """

    def __init__(self, ocean: OceanEnvironment):
        self.ocean    = ocean
        self.alerts: List[Alert]              = []
        self.vessels: List[CoastGuardVessel]  = []
        self.events:  List[dict]              = []
        self._alert_counter  = 0
        self._vessel_counter = 0
        self._first_detection_t: Optional[float] = None
        self.alert_active    = False
        self.detection_source: str = "none"

        # Pre-create ICG vessels at home ports
        self._create_vessels()

    def _create_vessels(self):
        for st in ICG_STATIONS:
            row, col = _lonlat_to_rc(st["lon"], st["lat"])
            # Clamp col to offshore edge (vessels are at port, just inside)
            col = float(np.clip(col, LAND_COLS + 1, LAND_COLS + 4))
            self.vessels.append(CoastGuardVessel(
                vessel_id=self._vessel_counter,
                name=st["name"],
                vessel_type=st["type"],
                row=row, col=col,
                home_row=row, home_col=col,
                target_row=row, target_col=col,
                t_mobilized=float('inf'),
                speed_ms=st["speed_kn"] * KNOTS_TO_MS,
                skim_rate=st["skim_rate"],
                skim_radius=st["skim_radius"],
                status="standby",
            ))
            self._vessel_counter += 1

    # ─────────────────────── Detection & Alerting ──────────────────────────

    def check_detection(self, oil_engine: OilSpillEngine,
                        sensor_nodes: list) -> Optional[Alert]:
        """
        Check three detection sources:
        1. WSN buoy in-situ sensors
        2. SAR satellite (if pass active)
        3. Aerial drone (if drone has oil reading)
        """
        if self.alert_active:
            return None

        source     = None
        spill_row  = GRID_H // 2
        spill_col  = GRID_W // 2
        node_id    = None
        max_conc   = 0.0

        # --- 1. WSN Buoy detection ---
        buoy_hits = [(n['id'], n['oil'], int(n['row']), int(n['col']))
                     for n in sensor_nodes
                     if n['oil'] > SENSOR_DETECTION_THRESHOLD
                     and n['alive'] and not n.get('is_sink') and not n.get('is_drone')]
        if buoy_hits:
            buoy_hits.sort(key=lambda x: -x[1])
            node_id, max_conc, spill_row, spill_col = buoy_hits[0]
            source = "WSN_BUOY"

        # --- 2. SAR satellite detection (more sensitive) ---
        if source is None and oil_engine.sar_detected:
            source    = "SAR_SATELLITE"
            max_conc  = float(np.max(oil_engine.C))
            peak      = np.unravel_index(np.argmax(oil_engine.C), oil_engine.C.shape)
            spill_row, spill_col = int(peak[0]), int(peak[1])

        # --- 3. Aerial drone detection ---
        if source is None:
            drone_hits = [(n['id'], n['oil'], int(n['row']), int(n['col']))
                          for n in sensor_nodes
                          if n.get('is_drone') and n['oil'] > 0.01]
            if drone_hits:
                drone_hits.sort(key=lambda x: -x[1])
                node_id, max_conc, spill_row, spill_col = drone_hits[0]
                source = "AERIAL_DRONE"

        if source is None:
            return None

        alert = Alert(
            alert_id=self._alert_counter,
            t_generated=self.ocean.t,
            spill_row=spill_row,
            spill_col=spill_col,
            max_concentration=round(max_conc, 4),
            detection_source=source,
            node_id_detected=node_id,
        )
        self.alerts.append(alert)
        self._alert_counter += 1
        self.alert_active    = True
        self.detection_source = source

        if self._first_detection_t is None:
            self._first_detection_t = self.ocean.t

        src_icon = {"WSN_BUOY": "🟡 Buoy", "SAR_SATELLITE": "🛰️ SAR",
                    "AERIAL_DRONE": "🚁 Drone"}.get(source, source)
        self.events.append({
            "t":    self.ocean.t,
            "type": "ALERT",
            "msg":  f"🚨 OIL SPILL DETECTED via {src_icon} | "
                    f"Conc: {max_conc:.4f} kg/m² | "
                    f"Area: {oil_engine.sar_slick_area_km2:.1f} km²",
            "row":  spill_row, "col": spill_col,
        })

        self._dispatch_vessels(alert)
        return alert

    # ─────────────────────── Vessel Dispatch ───────────────────────────────

    def _dispatch_vessels(self, alert: Alert):
        """Dispatch vessels sorted by proximity to spill."""
        t = self.ocean.t

        # Sort stations by distance to spill
        def dist_to_spill(v: CoastGuardVessel):
            return np.sqrt((v.row - alert.spill_row)**2 +
                           (v.col - alert.spill_col)**2)

        sorted_vessels = sorted(self.vessels, key=dist_to_spill)
        station_map    = {st["name"]: st for st in ICG_STATIONS}

        for i, vessel in enumerate(sorted_vessels):
            st = station_map.get(vessel.name)
            if st is None:
                continue
            delay = st["delay_s"]

            vessel.target_row  = float(alert.spill_row)
            vessel.target_col  = float(alert.spill_col)
            vessel.t_mobilized = t + delay
            vessel.status      = "dispatched"

        eta_min = min(st["delay_s"] for st in ICG_STATIONS) // 60
        self.events.append({
            "t": t, "type": "DISPATCH",
            "msg": (f"✅ {len(self.vessels)} ICG vessels dispatched. "
                    f"Fastest ETA ~{eta_min} min (ICGS Chennai FPV). "
                    f"SAR monitoring: {'ACTIVE' if self.ocean.sar_pass_active else 'STANDBY'}"),
            "row": alert.spill_row, "col": alert.spill_col,
        })

    # ─────────────────────── Agent Movement & Cleanup ──────────────────────

    def step(self, oil_engine: OilSpillEngine):
        dt = self.ocean.dt
        t  = self.ocean.t

        for vessel in self.vessels:
            if vessel.status == "standby":
                continue
            if t < vessel.t_mobilized:
                continue

            if not vessel.active:
                vessel.active = True
                vessel.status = "en_route"
                self.events.append({
                    "t": t, "type": "EN_ROUTE",
                    "msg": f"🚢 {vessel.name} now en-route to spill zone.",
                    "row": int(vessel.row), "col": int(vessel.col),
                })

            # Move toward target
            dr   = vessel.target_row - vessel.row
            dc   = vessel.target_col - vessel.col
            dist = max(np.sqrt(dr**2 + dc**2), 0.001)
            step = vessel.speed_cells_s * dt

            if dist > 1.0:
                vessel.row += (dr / dist) * min(step, dist)
                vessel.col += (dc / dist) * min(step, dist)
            else:
                if not vessel.on_site:
                    vessel.on_site = True
                    vessel.status  = "on_site"
                    self.events.append({
                        "t": t, "type": "ON_SITE",
                        "msg": f"⚓ {vessel.name} ON-SITE — commencing cleanup.",
                        "row": int(vessel.row), "col": int(vessel.col),
                    })

                # Apply mechanical skimming
                if vessel.skim_rate > 0 and vessel.skim_radius > 0:
                    area = max(np.pi * (vessel.skim_radius * (DX + DY) / 2)**2, 1.0)
                    removed = oil_engine.apply_adsorption(
                        int(np.clip(vessel.row, 0, GRID_H - 1)),
                        int(np.clip(vessel.col, 0, GRID_W - 1)),
                        vessel.skim_radius,
                        removed_kg_m2=vessel.skim_rate * dt / area,
                    )
                    vessel.oil_removed_kg += removed

            vessel.row = float(np.clip(vessel.row, 0, GRID_H - 1))
            vessel.col = float(np.clip(vessel.col, LAND_COLS + 1, GRID_W - 1))

    # ─────────────────────── Metrics ───────────────────────────────────────

    def get_metrics(self) -> dict:
        t     = self.ocean.t
        first = self._first_detection_t
        return {
            "total_alerts":       len(self.alerts),
            "alert_active":       self.alert_active,
            "detection_source":   self.detection_source,
            "total_vessels":      len(self.vessels),
            "active_vessels":     sum(1 for v in self.vessels if v.active),
            "on_site_vessels":    sum(1 for v in self.vessels if v.on_site),
            "first_detection_t":  round(first, 0) if first else None,
            "response_delay_h":   round((t - first) / 3600, 2) if first else 0.0,
            "total_skimmed_kg":   round(sum(v.oil_removed_kg for v in self.vessels), 1),
            "recent_events":      self.events[-12:],
        }

    def get_agents_list(self) -> list:
        return [
            {
                "id":         v.vessel_id,
                "type":       v.vessel_type,
                "name":       v.name,
                "row":        round(v.row, 2),
                "col":        round(v.col, 2),
                "target_row": v.target_row,
                "target_col": v.target_col,
                "active":     v.active,
                "on_site":    v.on_site,
                "status":     v.status,
                "removed_kg": round(v.oil_removed_kg, 1),
            }
            for v in self.vessels
        ]
