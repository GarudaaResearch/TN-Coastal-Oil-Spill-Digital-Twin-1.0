"""
Buoyant WSN + Aerial Drone Sensor Network — Bay of Bengal
==========================================================
Models offshore buoy sensor nodes deployed in Tamil Nadu coastal waters
and an aerial surveillance drone that overflies the spill zone.

Buoy clusters at real TN offshore positions:
  - Chennai Offshore  (13.1°N, 80.5°E)
  - Cuddalore         (11.7°N, 80.1°E)
  - Kaveri Delta      (10.8°N, 79.9°E)
  - Nagapattinam      (10.8°N, 80.0°E)
  - Palk Strait       (9.5°N,  79.7°E)
  - Gulf of Mannar    (9.0°N,  79.5°E)

Detection modes:
  1. In-situ buoy sensors (oil concentration, fluorescence)
  2. Aerial drone (visual + IR camera, lower threshold)

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from .ocean_model import (OceanEnvironment, GRID_W, GRID_H, DX, DY,
                          LON_MIN, LON_MAX, LAT_MIN, LAT_MAX, LAND_COLS)


# ─────────────────────────── Node Parameters ────────────────────────────────
BATTERY_CAPACITY_J  = 72_000.0   # 72 kJ — marine-grade LiFePO4 buoy battery
E_TX_PER_PKT_J      = 0.060      # 60 mJ / LoRa packet (long-range radio)
E_RX_PER_PKT_J      = 0.030      # 30 mJ / RX
E_IDLE_W            = 0.0008     # 0.8 mW idle (sensor + MCU)
COMM_RANGE_CELLS    = 15         # ~35 km communication range (LoRa)
FAIL_BETA           = 0.0005
E_REF_J             = 6_000.0
SINK_NODE_ID        = 0

# Drone parameters
DRONE_SPEED_MS      = 20.0       # m/s airspeed
DRONE_INTERVAL_TICKS= 20         # overfly every 20 ticks


def _lonlat_to_rc(lon: float, lat: float) -> Tuple[float, float]:
    """Convert geographic coordinates to fractional grid (row, col)."""
    col = (lon - LON_MIN) / (LON_MAX - LON_MIN) * GRID_W
    row = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * GRID_H
    return float(np.clip(row, 0, GRID_H - 1)), float(np.clip(col, 0, GRID_W - 1))


# Named offshore buoy deployment positions (lon, lat) with cluster sizes
BUOY_CLUSTERS = [
    ("Chennai Offshore",    80.50, 13.10, 6),
    ("Ennore Offshore",     80.40, 13.22, 4),
    ("Cuddalore Offshore",  80.10, 11.70, 5),
    ("Kaveri Delta",        79.90, 10.85, 4),
    ("Nagapattinam",        80.00, 10.77, 4),
    ("Palk Strait North",   79.80,  9.80, 5),
    ("Palk Strait South",   79.70,  9.30, 4),
    ("Gulf of Mannar",      79.55,  8.90, 5),
    ("Tuticorin Offshore",  78.30,  8.90, 3),   # ~west of grid edge, clamp
]


@dataclass
class SensorNode:
    node_id:         int
    row:             float
    col:             float
    cluster_name:    str = "unknown"
    energy_j:        float = BATTERY_CAPACITY_J
    alive:           bool  = True
    is_sink:         bool  = False
    is_drone:        bool  = False
    packets_sent:    int   = 0
    packets_received:int   = 0
    oil_reading:     float = 0.0
    next_hop:        Optional[int] = None
    route_pheromone: float = 1.0


class SensorNetwork:
    """
    Manages buoy WSN + aerial drone for Bay of Bengal oil spill detection.
    """

    def __init__(self, ocean: OceanEnvironment, n_nodes: int = 45, seed: int = 7):
        self.ocean = ocean
        self.rng   = np.random.default_rng(seed)
        self.nodes: List[SensorNode] = []
        self.tick  = 0
        self.adjacency: Dict[int, List[int]] = {}
        self._deploy_nodes()

    # ─────────────────────── Deployment ────────────────────────────────────

    def _deploy_nodes(self):
        """
        Deploy buoy clusters at real TN offshore positions.
        Node 0 = base station / coastal sink node near Chennai.
        Also add an aerial drone node (node 1).
        """
        node_id = 0

        # Sink node at Chennai port / coast guard station
        sink_row, sink_col = _lonlat_to_rc(80.30, 13.08)
        # Ensure it's at the shoreline edge (just offshore)
        sink_col = float(LAND_COLS + 2)
        self.nodes.append(SensorNode(
            node_id=node_id, row=sink_row, col=sink_col,
            cluster_name="Chennai CG Base",
            energy_j=float('inf'), is_sink=True
        ))
        node_id += 1

        # Aerial drone node (starts at Chennai, overflies periodically)
        drone_row, drone_col = _lonlat_to_rc(80.30, 13.08)
        self.nodes.append(SensorNode(
            node_id=node_id, row=drone_row, col=drone_col,
            cluster_name="ICG Aerial Drone",
            energy_j=float('inf'), is_drone=True
        ))
        self._drone_id       = node_id
        self._drone_target   = (drone_row, drone_col)
        self._drone_path_idx = 0
        node_id += 1

        # Buoy clusters at named positions with small random offsets
        for name, lon, lat, n in BUOY_CLUSTERS:
            base_row, base_col = _lonlat_to_rc(lon, lat)
            for i in range(n):
                r = base_row + self.rng.uniform(-2, 2)
                c = base_col + self.rng.uniform(-2, 2)
                r = float(np.clip(r, 0, GRID_H - 1))
                c = float(np.clip(c, LAND_COLS + 1, GRID_W - 1))
                # Skip if on land
                ri, ci = int(r), int(c)
                if self.ocean.land_mask[ri, ci] < 0.5:
                    c = float(LAND_COLS + 3)
                self.nodes.append(SensorNode(
                    node_id=node_id,
                    row=r, col=c,
                    cluster_name=name,
                    energy_j=BATTERY_CAPACITY_J,
                ))
                node_id += 1

    # ─────────────────────── Drone Path ────────────────────────────────────

    def _update_drone(self, dt: float):
        """Move drone in a sweeping pattern across the grid every DRONE_INTERVAL_TICKS."""
        drone = next((n for n in self.nodes if n.is_drone), None)
        if drone is None:
            return

        # Drone sweeps horizontally across the grid
        if self.tick % DRONE_INTERVAL_TICKS == 0:
            # Pick a new random scan line (different lat)
            target_row = float(self.rng.uniform(5, GRID_H - 5))
            target_col = float(GRID_W - 5)
            self._drone_target = (target_row, target_col)

        tr, tc = self._drone_target
        dr = tr - drone.row
        dc = tc - drone.col
        dist = max(np.sqrt(dr**2 + dc**2), 0.001)
        step_cells = (DRONE_SPEED_MS / DX) * dt

        if dist > 1.0:
            drone.row += (dr / dist) * min(step_cells, dist)
            drone.col += (dc / dist) * min(step_cells, dist)
        else:
            # Arrived — return to base
            sink = self.nodes[0]
            self._drone_target = (sink.row, sink.col)

        drone.row = float(np.clip(drone.row, 0, GRID_H - 1))
        drone.col = float(np.clip(drone.col, LAND_COLS, GRID_W - 1))

    # ─────────────────────── Physics Update ────────────────────────────────

    def _drift_node(self, node: SensorNode, u: np.ndarray, v: np.ndarray, dt: float):
        """Lagrangian Eulerian drift for buoy nodes."""
        if node.is_sink or node.is_drone:
            return
        r = int(np.clip(node.row, 0, GRID_H - 1))
        c = int(np.clip(node.col, 0, GRID_W - 1))
        u_n = float(u[r, c])
        v_n = float(v[r, c])

        node.col += (u_n / DX) * dt
        node.row += (v_n / DY) * dt
        node.row  = float(np.clip(node.row, 0, GRID_H - 1))
        node.col  = float(np.clip(node.col, LAND_COLS + 1, GRID_W - 1))

        # Bounce off land
        ri, ci = int(node.row), int(node.col)
        if self.ocean.land_mask[ri, ci] < 0.5:
            node.col = float(LAND_COLS + 2)

    def _energy_drain(self, node: SensorNode, dt: float):
        if not node.alive or node.is_sink or node.is_drone:
            return
        node.energy_j -= E_IDLE_W * dt
        if self.rng.random() < 0.1:
            node.energy_j  -= E_TX_PER_PKT_J
            node.packets_sent += 1
        node.energy_j = max(node.energy_j, 0.0)

    def _check_failure(self, node: SensorNode):
        if not node.alive or node.is_sink or node.is_drone:
            return
        if node.energy_j <= 0:
            node.alive = False
            return
        p_fail = FAIL_BETA * np.exp(-node.energy_j / E_REF_J)
        if self.rng.random() < p_fail:
            node.alive = False

    def _update_topology(self):
        alive = [n for n in self.nodes if n.alive]
        self.adjacency = {n.node_id: [] for n in alive}
        for i, ni in enumerate(alive):
            for nj in alive[i+1:]:
                dist = np.sqrt((ni.row - nj.row)**2 + (ni.col - nj.col)**2)
                if dist <= COMM_RANGE_CELLS:
                    self.adjacency[ni.node_id].append(nj.node_id)
                    self.adjacency[nj.node_id].append(ni.node_id)

    def update_readings(self, concentration_grid: np.ndarray):
        for node in self.nodes:
            if not node.alive:
                continue
            ri = int(np.clip(node.row, 0, GRID_H - 1))
            ci = int(np.clip(node.col, 0, GRID_W - 1))
            node.oil_reading = float(concentration_grid[ri, ci])

    def step(self):
        self.tick += 1
        u, v = self.ocean.get_current_field()
        dt   = self.ocean.dt

        for node in self.nodes:
            if not node.alive:
                continue
            self._drift_node(node, u, v, dt)
            self._energy_drain(node, dt)
            self._check_failure(node)

        self._update_drone(dt)
        self._update_topology()

    # ─────────────────────── Metrics & Serialization ────────────────────────

    def get_metrics(self) -> dict:
        buoys  = [n for n in self.nodes if not n.is_sink and not n.is_drone]
        alive  = [n for n in buoys if n.alive]
        total_energy = sum(n.energy_j for n in alive)
        init_energy  = len(buoys) * BATTERY_CAPACITY_J
        detecting    = [n for n in alive if n.oil_reading > 0.05]
        drone        = next((n for n in self.nodes if n.is_drone), None)
        return {
            "total_nodes":          len(self.nodes),
            "buoy_nodes":           len(buoys),
            "alive_nodes":          len(alive),
            "dead_nodes":           len(buoys) - len(alive),
            "network_energy_pct":   round(100 * total_energy / max(init_energy, 1), 1),
            "total_packets_sent":   sum(n.packets_sent for n in self.nodes),
            "connectivity_ratio":   round(len(alive) / max(len(buoys), 1), 3),
            "detecting_nodes":      len(detecting),
            "drone_row":            round(drone.row, 2) if drone else None,
            "drone_col":            round(drone.col, 2) if drone else None,
        }

    def get_nodes_list(self) -> list:
        return [
            {
                "id":       n.node_id,
                "row":      round(n.row, 2),
                "col":      round(n.col, 2),
                "energy":   BATTERY_CAPACITY_J if (n.is_sink or n.is_drone)
                            else round(n.energy_j, 1),
                "alive":    n.alive,
                "is_sink":  n.is_sink,
                "is_drone": n.is_drone,
                "cluster":  n.cluster_name,
                "oil":      round(n.oil_reading, 4),
                "next_hop": n.next_hop,
                "neighbors":self.adjacency.get(n.node_id, []),
            }
            for n in self.nodes
        ]
