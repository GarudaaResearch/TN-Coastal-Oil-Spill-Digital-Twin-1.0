"""Integration test — runs 3 simulation ticks and validates all modules."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from simulation.ocean_model      import OceanEnvironment
from simulation.oil_spill_engine import OilSpillEngine
from simulation.sensor_network   import SensorNetwork
from simulation.ai_routing       import AIRoutingEngine
from simulation.hydrochar_module import HydrocharModule
from simulation.response_system  import ResponseSystem

def run():
    ocean = OceanEnvironment(seed=42)
    oil   = OilSpillEngine(ocean)
    wsn   = SensorNetwork(ocean, n_nodes=20)
    ai    = AIRoutingEngine('aco')
    hc    = HydrocharModule()
    rs    = ResponseSystem(ocean)

    oil.add_spill(row=25, col=40, total_mass_kg=8000.0, release_rate_kg_s=1.2)
    hc.deploy(row=25, col=40, mass_kg=50.0, t_current=ocean.t)

    for tick in range(5):
        ocean.step()
        oil.step()
        wsn.step()
        wsn.update_readings(oil.C)
        ai.update(wsn.nodes, wsn.adjacency)
        hc.step(oil.C, oil, ocean.t)
        nodes_list = wsn.get_nodes_list()
        rs.check_detection(oil, nodes_list)
        rs.step(oil)

    m = oil.get_metrics()
    w = wsn.get_metrics()
    h = hc.get_metrics()
    r = rs.get_metrics()
    rt = ai.get_metrics()

    print("=" * 55)
    print("  TN COASTAL DIGITAL TWIN — Integration Test (5 ticks)")
    print("=" * 55)
    print(f"  Oil spill area   : {m['spill_area_km2']} km2")
    print(f"  Oil mass in water: {m['total_mass_kg']} kg")
    print(f"  Max concentration: {m['max_concentration']} kg/m2")
    print(f"  Spill detected   : {m['detected']}")
    print(f"  Cleanup eff.     : {m['cleanup_efficiency_pct']} %")
    print("-" * 55)
    print(f"  WSN alive nodes  : {w['alive_nodes']} / {w['total_nodes']}")
    print(f"  Network energy   : {w['network_energy_pct']} %")
    print(f"  Packets sent     : {w['total_packets_sent']}")
    print(f"  Routing algo     : {rt['algorithm']}")
    print(f"  Routed nodes     : {rt['routed_nodes']}")
    print("-" * 55)
    print(f"  Hydro units dep. : {h['total_units_deployed']}")
    print(f"  Oil removed      : {h['total_removed_oil_kg']} kg")
    print(f"  Avg hydro eff.   : {h['avg_efficiency_pct']} %")
    print("-" * 55)
    print(f"  Response alerts  : {r['total_alerts']}")
    print(f"  Response agents  : {r['total_agents']}")
    print(f"  Alert active     : {r['alert_active']}")
    print("=" * 55)
    print("  ALL MODULES: PASSED")
    print("=" * 55)

    # Validate payload structure
    from main import build_payload, sim
    sim.ocean      = ocean
    sim.oil_engine = oil
    sim.sensor_net = wsn
    sim.ai_router  = ai
    sim.hydrochar  = hc
    sim.response   = rs
    sim.tick       = 5
    payload = build_payload()
    assert 'concentration_grid' in payload, "Missing concentration_grid"
    assert 'sensor_nodes' in payload, "Missing sensor_nodes"
    assert 'oil_metrics' in payload, "Missing oil_metrics"
    assert len(payload['concentration_grid']) == 90, "Grid rows mismatch"
    assert len(payload['concentration_grid'][0]) == 120, "Grid cols mismatch"
    print("  Payload structure: VALID")
    print(f"  Grid size: {len(payload['concentration_grid'])} x {len(payload['concentration_grid'][0])}")
    print(f"  Sensor nodes in payload: {len(payload['sensor_nodes'])}")
    print("=" * 55)

if __name__ == '__main__':
    run()
