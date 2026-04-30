"""
Response & Decision Coordination System
========================================
Simulates the real-world multi-agency response workflow triggered
by oil spill detection from the WSN.

Workflow:
  1. Detection: sensor reading > threshold → ALERT generated
  2. Alert broadcast: maritime authority + district collectors notified
  3. Response delay:
       - Maritime vessel (offshore cleanup): ~2h operational delay
       - District shoreline team:            ~4h mobilisation delay
  4. Cleanup effect: vessels apply mechanical skimming in their vicinity
  5. Hydrochar deployment: auto-triggered in high-concentration zones

Response agent roles:
  - MaritimeVessel : offshore/deep water response, faster movement
  - ShorlineTeam   : nearshore/mangrove response, slower, targeted

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .ocean_model import OceanEnvironment, GRID_H, GRID_W, DX, DY
from .oil_spill_engine import OilSpillEngine, DETECTION_THRESHOLD


# ─────────────────────────── Timing Constants ───────────────────────────────
MARITIME_DELAY_S   = 2 * 3600    # 2 hours in seconds
SHORELINE_DELAY_S  = 4 * 3600    # 4 hours in seconds
VESSEL_SPEED_M_S   = 5.0         # maritime vessel ~10 knots
TEAM_SPEED_M_S     = 1.0         # shoreline team speed
SKIMMING_RATE_KG_S = 0.2         # mechanical skimming rate (kg/s)
SKIM_RADIUS_CELLS  = 6


@dataclass
class Alert:
    alert_id: int
    t_generated: float
    spill_row: int
    spill_col: int
    max_concentration: float
    node_id_detected: int
    acknowledged: bool = False


@dataclass
class ResponseAgent:
    agent_id: int
    agent_type: str           # "maritime" | "shoreline"
    row: float
    col: float
    target_row: float
    target_col: float
    t_mobilized: float        # simulation time when agent starts moving
    active: bool = False
    oil_removed_kg: float = 0.0
    speed_m_s: float = VESSEL_SPEED_M_S

    @property
    def speed_cells_s(self) -> float:
        return self.speed_m_s / DX


class ResponseSystem:
    """
    Manages spill detection alerts, response agent mobilisation,
    movement toward spill zones, and mechanical oil removal.
    """

    def __init__(self, ocean: OceanEnvironment):
        self.ocean = ocean
        self.alerts: List[Alert]          = []
        self.agents: List[ResponseAgent]  = []
        self.events: List[dict]           = []    # log for frontend
        self._alert_counter  = 0
        self._agent_counter  = 0
        self._first_detection_t: Optional[float] = None
        self._response_times: List[float] = []
        self.alert_active    = False

        # Maritime vessel starts at base port (top of grid)
        self._maritime_home  = (float(GRID_H - 10), float(GRID_W // 3))
        # Shoreline team starts near coast
        self._shoreline_home = (float(GRID_H // 2), float(GRID_W - 14))

    # ─────────────────────── Detection & Alerting ──────────────────────────

    def check_detection(self, oil_engine: OilSpillEngine,
                        sensor_nodes: list) -> Optional[Alert]:
        """
        Evaluate sensor readings and generate alert if threshold crossed.
        Returns new Alert if generated, else None.
        """
        # Find node with highest oil reading above threshold
        triggered = [(n['id'], n['oil']) for n in sensor_nodes
                     if n['oil'] > DETECTION_THRESHOLD and n['alive']]
        if not triggered:
            return None

        triggered.sort(key=lambda x: -x[1])
        best_node_id, best_reading = triggered[0]

        # Suppress duplicate alerts (only one active at a time)
        if self.alert_active:
            return None

        # Find node position
        node_data = next((n for n in sensor_nodes
                          if n['id'] == best_node_id), None)
        if node_data is None:
            return None

        alert = Alert(
            alert_id=self._alert_counter,
            t_generated=self.ocean.t,
            spill_row=int(node_data['row']),
            spill_col=int(node_data['col']),
            max_concentration=round(best_reading, 4),
            node_id_detected=best_node_id,
        )
        self.alerts.append(alert)
        self._alert_counter += 1
        self.alert_active = True

        if self._first_detection_t is None:
            self._first_detection_t = self.ocean.t

        self.events.append({
            "t": self.ocean.t,
            "type": "ALERT",
            "msg": f"🚨 OIL SPILL DETECTED by Node #{best_node_id} | "
                   f"Conc: {best_reading:.4f} kg/m²",
            "row": alert.spill_row,
            "col": alert.spill_col,
        })

        # Auto-dispatch response agents
        self._dispatch_agents(alert)
        return alert

    # ─────────────────────── Dispatch ──────────────────────────────────────

    def _dispatch_agents(self, alert: Alert):
        """Mobilise maritime and shoreline response agents."""
        t = self.ocean.t

        # Maritime vessel
        mv = ResponseAgent(
            agent_id=self._agent_counter,
            agent_type="maritime",
            row=self._maritime_home[0],
            col=self._maritime_home[1],
            target_row=float(alert.spill_row),
            target_col=float(alert.spill_col),
            t_mobilized=t + MARITIME_DELAY_S,
            speed_m_s=VESSEL_SPEED_M_S,
        )
        self.agents.append(mv)
        self._agent_counter += 1

        # Shoreline team
        st = ResponseAgent(
            agent_id=self._agent_counter,
            agent_type="shoreline",
            row=self._shoreline_home[0],
            col=self._shoreline_home[1],
            target_row=float(max(alert.spill_row, GRID_H - 15)),
            target_col=float(GRID_W - 14),
            t_mobilized=t + SHORELINE_DELAY_S,
            speed_m_s=TEAM_SPEED_M_S,
        )
        self.agents.append(st)
        self._agent_counter += 1

        self.events.append({
            "t": t,
            "type": "DISPATCH",
            "msg": f"✅ Maritime vessel dispatched (ETA ~{MARITIME_DELAY_S//3600}h). "
                   f"Shoreline team mobilising (ETA ~{SHORELINE_DELAY_S//3600}h).",
            "row": alert.spill_row, "col": alert.spill_col,
        })

    # ─────────────────────── Agent Movement & Cleanup ──────────────────────

    def step(self, oil_engine: OilSpillEngine):
        """Move agents toward target, apply mechanical skimming if on-site."""
        dt = self.ocean.dt
        t  = self.ocean.t

        for agent in self.agents:
            if t < agent.t_mobilized:
                continue
            if not agent.active:
                agent.active = True
                self.events.append({
                    "t": t,
                    "type": "ARRIVAL",
                    "msg": f"🚢 {agent.agent_type.title()} agent #{agent.agent_id} "
                           f"now en-route to spill zone.",
                    "row": int(agent.row), "col": int(agent.col),
                })

            # Move toward target
            dr = agent.target_row - agent.row
            dc = agent.target_col - agent.col
            dist = max(np.sqrt(dr**2 + dc**2), 0.001)
            step_cells = agent.speed_cells_s * dt
            if dist > 0.5:
                agent.row += (dr / dist) * min(step_cells, dist)
                agent.col += (dc / dist) * min(step_cells, dist)
            else:
                # On-site: apply mechanical skimming
                removed = oil_engine.apply_adsorption(
                    int(np.clip(agent.row, 0, GRID_H - 1)),
                    int(np.clip(agent.col, 0, GRID_W - 1)),
                    SKIM_RADIUS_CELLS,
                    removed_kg_m2=SKIMMING_RATE_KG_S * dt / (
                        np.pi * (SKIM_RADIUS_CELLS * DX)**2)
                )
                agent.oil_removed_kg += removed

    # ─────────────────────── Response Metrics ──────────────────────────────

    def get_metrics(self) -> dict:
        t = self.ocean.t
        first = self._first_detection_t
        response_delay = (t - first) if first is not None else 0.0
        maritime_on_site = any(
            a.active and a.agent_type == "maritime" and
            abs(a.row - a.target_row) < 1 for a in self.agents)
        return {
            "total_alerts":        len(self.alerts),
            "alert_active":        self.alert_active,
            "total_agents":        len(self.agents),
            "active_agents":       sum(1 for a in self.agents if a.active),
            "first_detection_t":   round(first, 0) if first else None,
            "response_delay_h":    round(response_delay / 3600, 2),
            "total_skimmed_kg":    round(
                sum(a.oil_removed_kg for a in self.agents), 1),
            "recent_events":       self.events[-10:],
        }

    def get_agents_list(self) -> list:
        return [
            {
                "id":         a.agent_id,
                "type":       a.agent_type,
                "row":        round(a.row, 2),
                "col":        round(a.col, 2),
                "target_row": a.target_row,
                "target_col": a.target_col,
                "active":     a.active,
                "removed_kg": round(a.oil_removed_kg, 1),
            }
            for a in self.agents
        ]
