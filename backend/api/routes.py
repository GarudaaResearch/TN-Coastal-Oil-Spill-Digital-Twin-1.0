"""
REST API Routes — TN Coastal Digital Twin
==========================================
All simulation control endpoints.

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
import numpy as np

router = APIRouter()
sim = None   # injected by main.py


# ─────────────────────────── Request Models ──────────────────────────────────

class StartRequest(BaseModel):
    seed:      int = 42
    n_nodes:   int = Field(40, ge=5, le=100)
    algorithm: str = "aco"


class SpillRequest(BaseModel):
    row:              int = Field(45, ge=0)
    col:              int = Field(60, ge=0)
    total_mass_kg:    float = Field(5000.0, gt=0)
    release_rate_kg_s: float = Field(0.5, gt=0)


class HydrocharRequest(BaseModel):
    row:     int = Field(45, ge=0)
    col:     int = Field(60, ge=0)
    mass_kg: float = Field(50.0, gt=0)


class AlgorithmRequest(BaseModel):
    algorithm: str = "aco"   # "greedy" | "aco" | "qlearn"


# ─────────────────────────── Endpoints ──────────────────────────────────────

@router.post("/simulation/start")
async def start_simulation(req: StartRequest):
    sim.reset(seed=req.seed, n_nodes=req.n_nodes, algorithm=req.algorithm)
    sim.running = True

    # Auto-inject a default spill at Gulf of Mannar zone
    sim.oil_engine.add_spill(row=25, col=40,
                             total_mass_kg=8000.0,
                             release_rate_kg_s=1.2)
    return {"status": "started", "algorithm": req.algorithm,
            "nodes": req.n_nodes}


@router.post("/simulation/stop")
async def stop_simulation():
    sim.running = False
    return {"status": "stopped", "tick": sim.tick}


@router.post("/simulation/resume")
async def resume_simulation():
    sim.running = True
    return {"status": "resumed", "tick": sim.tick}


@router.post("/spill/inject")
async def inject_spill(req: SpillRequest):
    from simulation.ocean_model import GRID_H, GRID_W
    row = int(np.clip(req.row, 0, GRID_H - 1))
    col = int(np.clip(req.col, 0, GRID_W - 1))
    ev = sim.oil_engine.add_spill(
        row=row, col=col,
        total_mass_kg=req.total_mass_kg,
        release_rate_kg_s=req.release_rate_kg_s,
    )
    return {
        "status": "spill_injected",
        "row": row, "col": col,
        "total_mass_kg": req.total_mass_kg,
    }


@router.post("/hydrochar/deploy")
async def deploy_hydrochar(req: HydrocharRequest):
    from simulation.ocean_model import GRID_H, GRID_W
    row = int(np.clip(req.row, 0, GRID_H - 1))
    col = int(np.clip(req.col, 0, GRID_W - 1))
    unit = sim.hydrochar.deploy(row=row, col=col,
                                mass_kg=req.mass_kg,
                                t_current=sim.ocean.t)
    if unit is None:
        return {"status": "error", "msg": "Insufficient hydrochar stockpile"}
    return {
        "status": "deployed",
        "unit_id": unit.unit_id,
        "row": row, "col": col,
        "mass_kg": req.mass_kg,
    }


@router.post("/routing/algorithm")
async def set_algorithm(req: AlgorithmRequest):
    sim.ai_router.set_algorithm(req.algorithm)
    return {
        "status": "algorithm_changed",
        "algorithm": sim.ai_router.algorithm_name,
    }


@router.get("/metrics")
async def get_metrics():
    return {
        "tick":      sim.tick,
        "t_hours":   round(sim.ocean.t / 3600, 2),
        "running":   sim.running,
        "oil":       sim.oil_engine.get_metrics(),
        "wsn":       sim.sensor_net.get_metrics(),
        "routing":   sim.ai_router.get_metrics(),
        "hydrochar": sim.hydrochar.get_metrics(),
        "response":  sim.response.get_metrics(),
    }


@router.get("/state/snapshot")
async def get_snapshot():
    """Returns last broadcast payload."""
    return sim.last_payload if sim.last_payload else {"error": "No state yet"}


@router.get("/health")
async def health():
    return {"status": "ok", "tick": sim.tick, "running": sim.running}
