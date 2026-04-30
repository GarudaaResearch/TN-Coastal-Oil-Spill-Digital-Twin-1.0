"""
AI Routing Engine — Bio-Adaptive Routing for Buoyant WSN
=========================================================
Implements two routing strategies:

1. BASELINE — Greedy Energy-Aware Routing (GEA-R):
   Next-hop = alive neighbor with maximum residual energy
   closer to the sink. Simple, O(degree) computation.

2. ADVANCED — Ant Colony Optimization (ACO) Routing:
   Pheromone trails τ(i,j) encode historically good paths.
   Heuristic η(i,j) = energy_j / distance_to_sink_j (energetically
   efficient and geographically progressive).
   
   Update rule:
       τ(i,j) ← (1 - ρ) · τ(i,j) + Δτ(i,j)
       Δτ(i,j) = Q / path_cost  if (i,j) on best path this round

3. BONUS — Q-Learning Adaptive Routing:
   State  s  = (energy_bin, neighbor_count, oil_reading_bin)  [discrete]
   Action a  = next_hop neighbor index
   Reward r  = +10 if delivered, -1 per hop, -5 if dead end
   ε-greedy exploration; tabular Q-table with linear decay of ε.

All algorithms share the same interface: compute_routes(nodes, adjacency) → dict

Author : Prof. Anjit Raja R, ANJIT SCHOOL OF AI & ISC-RCAS
Date   : 2026
"""

from __future__ import annotations
import numpy as np
from typing import List, Dict, Optional, Tuple
from .sensor_network import SensorNode, SINK_NODE_ID, BATTERY_CAPACITY_J


# ─────────────────────────── ACO Parameters ─────────────────────────────────
ACO_ALPHA      = 1.0    # pheromone weight
ACO_BETA       = 2.5    # heuristic weight
ACO_RHO        = 0.05   # evaporation rate
ACO_Q          = 100.0  # pheromone deposit constant
ACO_N_ANTS     = 15     # ants per iteration
ACO_ITERATIONS = 5      # iterations per routing update

# Q-Learning parameters
QL_ALPHA       = 0.1    # learning rate
QL_GAMMA       = 0.95   # discount factor
QL_EPSILON_MAX = 0.3    # initial exploration
QL_EPSILON_MIN = 0.01
QL_DECAY       = 0.998


def _sink_distance(node: SensorNode, sink_row: float, sink_col: float) -> float:
    return np.sqrt((node.row - sink_row)**2 + (node.col - sink_col)**2)


# ═══════════════════════════════════════════════════════════════════════════
class GreedyRouter:
    """
    Greedy Energy-Aware Routing (GEA-R) — Baseline.
    Each alive node routes to its alive neighbor with maximum residual
    energy that is closer to the sink.
    """

    name = "GEA-R (Baseline)"

    def compute_routes(self,
                       nodes: List[SensorNode],
                       adjacency: Dict[int, List[int]]) -> Dict[int, Optional[int]]:
        node_map = {n.node_id: n for n in nodes if n.alive}
        sink = node_map.get(SINK_NODE_ID)
        if sink is None:
            return {}

        routes: Dict[int, Optional[int]] = {}
        for node in nodes:
            if not node.alive or node.is_sink:
                continue
            neighbors = adjacency.get(node.node_id, [])
            alive_neighbors = [node_map[nid] for nid in neighbors
                               if nid in node_map]
            if not alive_neighbors:
                routes[node.node_id] = None
                continue
            # Filter: neighbor must be closer to sink
            d_self = _sink_distance(node, sink.row, sink.col)
            candidates = [n for n in alive_neighbors
                          if _sink_distance(n, sink.row, sink.col) < d_self]
            if not candidates:
                candidates = alive_neighbors   # no progressive hop available
            best = max(candidates, key=lambda n: n.energy_j)
            routes[node.node_id] = best.node_id

        return routes


# ═══════════════════════════════════════════════════════════════════════════
class ACORouter:
    """
    Ant Colony Optimization Routing.
    Pheromone matrix τ[i][j] is maintained between node pairs.
    """

    name = "ACO (Advanced)"

    def __init__(self):
        self.pheromone: Dict[Tuple[int, int], float] = {}
        self.last_routes: Dict[int, Optional[int]] = {}

    def _tau(self, i: int, j: int) -> float:
        return self.pheromone.get((i, j), 1.0)

    def _eta(self, node_j: SensorNode, sink_row: float, sink_col: float) -> float:
        """Heuristic: energy / distance_to_sink (higher is better)."""
        d = max(_sink_distance(node_j, sink_row, sink_col), 0.001)
        # Cap energy at battery capacity for sink node (infinite energy)
        energy = min(node_j.energy_j, BATTERY_CAPACITY_J)
        return max(energy / (BATTERY_CAPACITY_J * d), 1e-9)

    def compute_routes(self,
                       nodes: List[SensorNode],
                       adjacency: Dict[int, List[int]]) -> Dict[int, Optional[int]]:
        node_map = {n.node_id: n for n in nodes if n.alive}
        sink = node_map.get(SINK_NODE_ID)
        if sink is None:
            return {}

        best_routes: Dict[int, Optional[int]] = {}
        best_cost: Dict[int, float] = {}

        for _ in range(ACO_ITERATIONS):
            for _ in range(ACO_N_ANTS):
                # Each ant starts from a random source node
                sources = [n for n in nodes
                           if n.alive and not n.is_sink]
                if not sources:
                    break
                ant_start = node_map[np.random.choice([s.node_id for s in sources])]
                path, cost = self._ant_walk(ant_start, sink, node_map,
                                            adjacency)
                if path and len(path) > 1:
                    deposit = ACO_Q / max(cost, 1.0)
                    for k in range(len(path) - 1):
                        key = (path[k], path[k+1])
                        self.pheromone[key] = self.pheromone.get(key, 1.0) + deposit
                    # Update best known route for source
                    src_id = path[0]
                    if src_id not in best_cost or cost < best_cost[src_id]:
                        best_cost[src_id] = cost
                        best_routes[src_id] = path[1] if len(path) > 1 else None

        # Pheromone evaporation
        for key in list(self.pheromone.keys()):
            self.pheromone[key] *= (1 - ACO_RHO)
            if self.pheromone[key] < 0.01:
                del self.pheromone[key]

        # Fill missing routes with greedy fallback
        greedy = GreedyRouter()
        fallback = greedy.compute_routes(nodes, adjacency)
        for node in nodes:
            if node.alive and not node.is_sink:
                if node.node_id not in best_routes:
                    best_routes[node.node_id] = fallback.get(node.node_id)

        self.last_routes = best_routes
        return best_routes

    def _ant_walk(self, start: SensorNode, sink: SensorNode,
                  node_map: Dict[int, SensorNode],
                  adjacency: Dict[int, List[int]]) -> Tuple[List[int], float]:
        """Walk from start toward sink using τ·η selection."""
        path = [start.node_id]
        visited = {start.node_id}
        cost = 0.0
        current = start
        max_hops = 20

        while current.node_id != sink.node_id and len(path) <= max_hops:
            neighbors = [node_map[nid] for nid in adjacency.get(current.node_id, [])
                         if nid in node_map and nid not in visited]
            if not neighbors:
                return path, float('inf')   # dead end

            # Probabilistic selection
            probs = []
            for nb in neighbors:
                tau = self._tau(current.node_id, nb.node_id)
                eta = self._eta(nb, sink.row, sink.col)
                probs.append((tau ** ACO_ALPHA) * (eta ** ACO_BETA))
            probs = np.array(probs, dtype=np.float64)
            total = probs.sum()
            if total <= 0 or not np.isfinite(total):
                # Fallback: uniform probability
                probs = np.ones(len(neighbors)) / len(neighbors)
            else:
                probs /= total
            # Final NaN guard
            probs = np.nan_to_num(probs, nan=1.0/len(neighbors))
            probs /= probs.sum()

            chosen = neighbors[np.random.choice(len(neighbors), p=probs)]
            path.append(chosen.node_id)
            visited.add(chosen.node_id)
            cost += E_TX_COST(current, chosen)
            current = chosen

        return path, cost


def E_TX_COST(sender: SensorNode, receiver: SensorNode) -> float:
    """Energy cost proxy: distance-based free-space path loss."""
    d = np.sqrt((sender.row - receiver.row)**2 + (sender.col - receiver.col)**2)
    return 0.050 * (1 + 0.01 * d**2)   # J


# ═══════════════════════════════════════════════════════════════════════════
class QLearningRouter:
    """
    Tabular Q-Learning router.
    State: tuple(energy_bin [0-4], neighbor_count [0-4], oil_bin [0-2])
    Action: index into sorted neighbor list (0 = nearest to sink)
    """

    name = "Q-Learning (RL)"

    def __init__(self):
        self.Q: Dict[tuple, np.ndarray] = {}
        self.epsilon = QL_EPSILON_MAX
        self.episode = 0

    def _state(self, node: SensorNode, neighbors: List[SensorNode]) -> tuple:
        e_bin  = int(np.clip(node.energy_j / BATTERY_CAPACITY_J * 5, 0, 4))
        n_bin  = int(np.clip(len(neighbors), 0, 4))
        oil_bin = int(np.clip(node.oil_reading * 10, 0, 2))
        return (e_bin, n_bin, oil_bin)

    def _get_q(self, state: tuple, n_actions: int) -> np.ndarray:
        if state not in self.Q:
            self.Q[state] = np.zeros(n_actions)
        elif len(self.Q[state]) < n_actions:
            diff = n_actions - len(self.Q[state])
            self.Q[state] = np.concatenate([self.Q[state], np.zeros(diff)])
        return self.Q[state][:n_actions]

    def compute_routes(self,
                       nodes: List[SensorNode],
                       adjacency: Dict[int, List[int]]) -> Dict[int, Optional[int]]:
        node_map = {n.node_id: n for n in nodes if n.alive}
        sink = node_map.get(SINK_NODE_ID)
        if sink is None:
            return {}

        routes: Dict[int, Optional[int]] = {}
        self.epsilon = max(QL_EPSILON_MIN,
                           self.epsilon * QL_DECAY)

        for node in nodes:
            if not node.alive or node.is_sink:
                continue
            nbr_ids  = adjacency.get(node.node_id, [])
            neighbors = sorted(
                [node_map[nid] for nid in nbr_ids if nid in node_map],
                key=lambda n: _sink_distance(n, sink.row, sink.col)
            )
            if not neighbors:
                routes[node.node_id] = None
                continue

            n_actions = len(neighbors)
            state     = self._state(node, neighbors)
            q_vals    = self._get_q(state, n_actions)

            # ε-greedy action selection
            if np.random.random() < self.epsilon:
                action = np.random.randint(n_actions)
            else:
                action = int(np.argmax(q_vals))

            chosen = neighbors[action]
            routes[node.node_id] = chosen.node_id

            # Online update: reward = energy saved + delivery progress
            reward = (chosen.energy_j / BATTERY_CAPACITY_J) * 10 - 1
            next_state = self._state(chosen, [])
            next_q_max = np.max(self._get_q(next_state, 1))
            q_vals[action] += QL_ALPHA * (
                reward + QL_GAMMA * next_q_max - q_vals[action]
            )

        self.episode += 1
        return routes


# ═══════════════════════════════════════════════════════════════════════════
class AIRoutingEngine:
    """
    Facade class that manages the active routing algorithm and
    applies computed routes back to sensor nodes.
    """

    ALGORITHMS = {
        "greedy": GreedyRouter,
        "aco":    ACORouter,
        "qlearn": QLearningRouter,
    }

    def __init__(self, algorithm: str = "aco"):
        self.set_algorithm(algorithm)
        self.current_routes: Dict[int, Optional[int]] = {}
        self.routing_events: int = 0

    def set_algorithm(self, algorithm: str):
        algo_cls = self.ALGORITHMS.get(algorithm, ACORouter)
        self.router = algo_cls()
        self.algorithm_name = self.router.name

    def update(self, nodes: List[SensorNode],
               adjacency: Dict[int, List[int]]):
        """Run routing algorithm and update node.next_hop fields."""
        routes = self.router.compute_routes(nodes, adjacency)
        self.current_routes = routes
        self.routing_events += 1

        for node in nodes:
            node.next_hop = routes.get(node.node_id)

    def get_metrics(self) -> dict:
        routed = sum(1 for v in self.current_routes.values() if v is not None)
        return {
            "algorithm":      self.algorithm_name,
            "routed_nodes":   routed,
            "unrouted_nodes": sum(1 for v in self.current_routes.values()
                                  if v is None),
            "routing_events": self.routing_events,
        }
