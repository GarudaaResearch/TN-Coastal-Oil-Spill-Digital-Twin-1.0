"""
Buoyant Wireless Sensor Network (WSN) Simulation
=================================================
Models floating sensor nodes deployed in Tamil Nadu coastal waters.

Node physics:
  - Position drifts with ocean surface current field (Lagrangian particle)
  - Energy budget: battery_J depletes via TX/RX/idle power draw
  - Failure model: stochastic Bernoulli P(fail) = β · exp(-E / E_ref)
  - Communication: graph edge formed if Euclidean distance < R_comm cells

Energy model (IEEE 802.15.4 / LoRa hybrid):
  - E_TX  = 50 mJ per packet transmission
  - E_RX  = 30 mJ per packet reception
  - E_idle = 0.5 mJ/s (sensor sampling + MCU idle)

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from .ocean_model import OceanEnvironment, GRID_W, GRID_H, DX, DY


# ─────────────────────────── Node Parameters ────────────────────────────────
BATTERY_CAPACITY_J   = 50_000.0   # 50 kJ ≈ LiFePO4 cell
E_TX_PER_PKT_J       = 0.050      # 50 mJ / packet
E_RX_PER_PKT_J       = 0.030      # 30 mJ / packet
E_IDLE_W             = 0.0005     # 0.5 mW idle draw (W = J/s)
COMM_RANGE_CELLS     = 12         # communication range in grid cells
FAIL_BETA            = 0.001      # stochastic failure coefficient
E_REF_J              = 5_000.0    # energy reference for failure curve
SINK_NODE_ID         = 0          # node 0 is the static base station / buoy


@dataclass
class SensorNode:
    node_id: int
    row: float           # current fractional grid row
    col: float           # current fractional grid col
    energy_j: float = BATTERY_CAPACITY_J
    alive: bool = True
    is_sink: bool = False
    packets_sent: int = 0
    packets_received: int = 0
    oil_reading: float = 0.0     # local oil concentration reading
    # For routing
    next_hop: Optional[int] = None
    route_pheromone: float = 1.0


class SensorNetwork:
    """
    Manages the full WSN: node lifecycle, drift physics,
    topology graph, and per-node data collection.
    """

    def __init__(self, ocean: OceanEnvironment, n_nodes: int = 40,
                 seed: int = 7):
        self.ocean = ocean
        self.rng = np.random.default_rng(seed)
        self.nodes: List[SensorNode] = []
        self.tick = 0
        self._deploy_nodes(n_nodes)
        self.adjacency: Dict[int, List[int]] = {}   # updated each step

    # ─────────────────────── Deployment ────────────────────────────────────

    def _deploy_nodes(self, n: int):
        """
        Deploy nodes randomly in ocean cells (land_mask = 1).
        Node 0 is the fixed base-station / sink buoy near shore.
        """
        land = self.ocean.land_mask
        ocean_cells = np.argwhere(land > 0.5)   # (row, col) pairs

        # Sink node near central coast
        self.nodes.append(SensorNode(
            node_id=0,
            row=float(GRID_H // 2),
            col=float(GRID_W - 12),
            energy_j=float('inf'),    # shore station has mains power
            is_sink=True
        ))

        # Randomly place remaining nodes
        chosen = self.rng.choice(len(ocean_cells), size=n - 1, replace=False)
        for idx, cell_idx in enumerate(chosen, start=1):
            r, c = ocean_cells[cell_idx]
            self.nodes.append(SensorNode(
                node_id=idx,
                row=float(r) + self.rng.uniform(-0.4, 0.4),
                col=float(c) + self.rng.uniform(-0.4, 0.4),
            ))

    # ─────────────────────── Physics Update ────────────────────────────────

    def _drift_node(self, node: SensorNode, u: np.ndarray, v: np.ndarray,
                    dt: float):
        """
        Lagrangian particle drift: bilinear interpolation of current field.
        """
        if node.is_sink:
            return
        r, c = int(np.clip(node.row, 0, GRID_H - 1)), \
               int(np.clip(node.col, 0, GRID_W - 1))

        u_node = float(u[r, c])
        v_node = float(v[r, c])

        # Convert m/s → cells/s, then × dt
        node.col += (u_node / DX) * dt
        node.row += (v_node / DY) * dt

        # Clamp to ocean area
        node.row = float(np.clip(node.row, 0, GRID_H - 1))
        node.col = float(np.clip(node.col, 0, GRID_W - 1))

        # If drifted onto land, bounce back
        ri, ci = int(node.row), int(node.col)
        if self.ocean.land_mask[ri, ci] < 0.5:
            node.row = float(np.clip(node.row - 2 * (v_node / DY) * dt,
                                     0, GRID_H - 1))
            node.col = float(np.clip(node.col - 2 * (u_node / DX) * dt,
                                     0, GRID_W - 1))

    def _energy_drain(self, node: SensorNode, dt: float):
        """Idle power drain + probabilistic TX event."""
        if not node.alive or node.is_sink:
            return
        node.energy_j -= E_IDLE_W * dt
        # Probabilistic packet send (once per ~10 steps)
        if self.rng.random() < 0.1:
            node.energy_j -= E_TX_PER_PKT_J
            node.packets_sent += 1
        node.energy_j = max(node.energy_j, 0.0)

    def _check_failure(self, node: SensorNode):
        """Stochastic failure: probability increases as energy depletes."""
        if not node.alive or node.is_sink:
            return
        if node.energy_j <= 0:
            node.alive = False
            return
        p_fail = FAIL_BETA * np.exp(-node.energy_j / E_REF_J)
        if self.rng.random() < p_fail:
            node.alive = False

    # ─────────────────────── Topology Graph ────────────────────────────────

    def _update_topology(self):
        """Build adjacency list based on Euclidean distance < COMM_RANGE_CELLS."""
        alive_nodes = [n for n in self.nodes if n.alive]
        self.adjacency = {n.node_id: [] for n in alive_nodes}
        for i, ni in enumerate(alive_nodes):
            for nj in alive_nodes[i+1:]:
                dist = np.sqrt((ni.row - nj.row)**2 + (ni.col - nj.col)**2)
                if dist <= COMM_RANGE_CELLS:
                    self.adjacency[ni.node_id].append(nj.node_id)
                    self.adjacency[nj.node_id].append(ni.node_id)

    # ─────────────────────── Sensing ───────────────────────────────────────

    def update_readings(self, concentration_grid: np.ndarray):
        """Sample oil concentration at each node's location."""
        for node in self.nodes:
            if not node.alive:
                continue
            ri = int(np.clip(node.row, 0, GRID_H - 1))
            ci = int(np.clip(node.col, 0, GRID_W - 1))
            node.oil_reading = float(concentration_grid[ri, ci])

    # ─────────────────────── Main Step ─────────────────────────────────────

    def step(self):
        """Advance WSN one simulation tick."""
        self.tick += 1
        u, v = self.ocean.get_current_field()
        dt = self.ocean.dt

        for node in self.nodes:
            if not node.alive:
                continue
            self._drift_node(node, u, v, dt)
            self._energy_drain(node, dt)
            self._check_failure(node)

        self._update_topology()

    # ─────────────────────── Metrics & Serialization ───────────────────────

    def get_metrics(self) -> dict:
        alive = [n for n in self.nodes if n.alive]
        total_energy = sum(n.energy_j for n in alive if not n.is_sink)
        init_energy  = (len(self.nodes) - 1) * BATTERY_CAPACITY_J
        return {
            "total_nodes":    len(self.nodes),
            "alive_nodes":    len(alive),
            "dead_nodes":     len(self.nodes) - len(alive),
            "network_energy_pct": round(100 * total_energy / max(init_energy, 1), 1),
            "total_packets_sent": sum(n.packets_sent for n in self.nodes),
            "connectivity_ratio": round(
                len(alive) / max(len(self.nodes), 1), 3),
        }

    def get_nodes_list(self) -> list:
        return [
            {
                "id":      n.node_id,
                "row":     round(n.row, 2),
                "col":     round(n.col, 2),
                # Cap at BATTERY_CAPACITY_J for JSON safety (sink has inf energy)
                "energy":  BATTERY_CAPACITY_J if n.is_sink else round(n.energy_j, 1),
                "alive":   n.alive,
                "is_sink": n.is_sink,
                "oil":     round(n.oil_reading, 4),
                "next_hop": n.next_hop,
                "neighbors": self.adjacency.get(n.node_id, []),
            }
            for n in self.nodes
        ]
