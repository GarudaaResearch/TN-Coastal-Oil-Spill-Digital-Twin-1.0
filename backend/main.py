"""
FastAPI Main — TN Coastal Oil Spill Digital Twin
=================================================
Entry point: WebSocket streaming + REST API.

WebSocket stream (ws://localhost:8000/ws/simulation):
  Broadcasts full simulation state JSON at ~2 Hz.

REST API:
  POST /api/simulation/start        – initialise / reset simulation
  POST /api/simulation/stop         – pause simulation
  POST /api/spill/inject            – inject a new oil spill event
  POST /api/hydrochar/deploy        – deploy hydrochar at location
  POST /api/routing/algorithm       – switch routing algorithm
  GET  /api/metrics                 – latest snapshot metrics
  GET  /api/state                   – full state snapshot

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from simulation.ocean_model      import OceanEnvironment
from simulation.oil_spill_engine import OilSpillEngine
from simulation.sensor_network   import SensorNetwork
from simulation.ai_routing       import AIRoutingEngine
from simulation.hydrochar_module import HydrocharModule
from simulation.response_system  import ResponseSystem
from api.routes                  import router


# ─────────────────────────── Global Simulation State ────────────────────────

class SimulationState:
    def __init__(self):
        self.running      = False
        self.tick         = 0
        self.ocean        = OceanEnvironment(seed=42)
        self.oil_engine   = OilSpillEngine(self.ocean)
        self.sensor_net   = SensorNetwork(self.ocean, n_nodes=40)
        self.ai_router    = AIRoutingEngine(algorithm="aco")
        self.hydrochar    = HydrocharModule()
        self.response     = ResponseSystem(self.ocean)
        self.ws_clients   = set()
        self.last_payload = {}

    def reset(self, seed: int = 42, n_nodes: int = 40, algorithm: str = "aco"):
        self.ocean      = OceanEnvironment(seed=seed)
        self.oil_engine = OilSpillEngine(self.ocean)
        self.sensor_net = SensorNetwork(self.ocean, n_nodes=n_nodes)
        self.ai_router  = AIRoutingEngine(algorithm=algorithm)
        self.hydrochar  = HydrocharModule()
        self.response   = ResponseSystem(self.ocean)
        self.tick       = 0
        self.running    = False


sim = SimulationState()


# ─────────────────────────── Simulation Loop ────────────────────────────────

async def simulation_loop():
    """Main async loop: advances simulation and broadcasts to WebSocket clients."""
    TICK_INTERVAL = 0.5   # seconds between ticks (2 Hz)

    while True:
        if sim.running:
            try:
                # --- Advance all modules ---
                sim.ocean.step()
                sim.oil_engine.step()
                sim.sensor_net.step()
                sim.sensor_net.update_readings(sim.oil_engine.C)

                # AI routing update (every 5 ticks for performance)
                if sim.tick % 5 == 0:
                    sim.ai_router.update(
                        sim.sensor_net.nodes,
                        sim.sensor_net.adjacency
                    )

                # Hydrochar adsorption
                sim.hydrochar.step(
                    sim.oil_engine.C,
                    sim.oil_engine,
                    sim.ocean.t
                )

                # Response system
                nodes_list = sim.sensor_net.get_nodes_list()
                sim.response.check_detection(sim.oil_engine, nodes_list)
                sim.response.step(sim.oil_engine)

                sim.tick += 1

                # --- Compose payload ---
                payload = build_payload()
                sim.last_payload = payload
                msg = json.dumps(payload)

                # Broadcast to all connected WebSocket clients
                dead_clients = set()
                for ws in sim.ws_clients:
                    try:
                        await ws.send_text(msg)
                    except Exception:
                        dead_clients.add(ws)
                sim.ws_clients -= dead_clients

            except Exception as e:
                print(f"[SIM ERROR] tick {sim.tick}: {e}")

        await asyncio.sleep(TICK_INTERVAL)


def build_payload() -> dict:
    """Assemble full simulation state for WebSocket broadcast."""
    return {
        "tick":        sim.tick,
        "t_seconds":   round(sim.ocean.t, 0),
        "t_hours":     round(sim.ocean.t / 3600, 2),
        "running":     sim.running,

        # Grid data
        "concentration_grid": sim.oil_engine.get_concentration_grid(),
        "sensitivity_grid":   sim.ocean.sensitivity.tolist(),
        "land_mask":          sim.ocean.land_mask.tolist(),

        # Module metrics
        "oil_metrics":      sim.oil_engine.get_metrics(),
        "wsn_metrics":      sim.sensor_net.get_metrics(),
        "routing_metrics":  sim.ai_router.get_metrics(),
        "hydrochar_metrics": sim.hydrochar.get_metrics(),
        "response_metrics": sim.response.get_metrics(),

        # Agent/entity lists
        "sensor_nodes":     sim.sensor_net.get_nodes_list(),
        "hydrochar_units":  sim.hydrochar.get_units_list(),
        "response_agents":  sim.response.get_agents_list(),

        # Environment
        "wind_speed":  round(sim.ocean.wind_speed_ms, 2),
        "wind_dir":    round(float(__import__('numpy').rad2deg(
                            sim.ocean.wind_dir_rad)) % 360, 1),
    }


# ─────────────────────────── App Lifecycle ──────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()


app = FastAPI(
    title="TN Coastal Oil Spill Digital Twin",
    description="AI-Driven Bio-Adaptive Routing in Buoyant WSN — Real-Time Simulation",
    version="2026.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach REST API router, injecting sim state
app.include_router(router, prefix="/api")


# Make sim accessible to routes module
import api.routes as _routes
_routes.sim = sim


# ─────────────────────────── WebSocket Endpoint ─────────────────────────────

@app.websocket("/ws/simulation")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    sim.ws_clients.add(websocket)
    try:
        # Send immediate state snapshot on connection
        if sim.last_payload:
            await websocket.send_text(json.dumps(sim.last_payload))
        while True:
            await websocket.receive_text()   # keep alive, handle pings
    except WebSocketDisconnect:
        sim.ws_clients.discard(websocket)
    except Exception:
        sim.ws_clients.discard(websocket)


@app.get("/")
async def root():
    return {
        "system": "TN Coastal Oil Spill Digital Twin",
        "version": "2026.1",
        "author": "Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS",
        "status": "running" if sim.running else "paused",
        "tick": sim.tick,
    }
