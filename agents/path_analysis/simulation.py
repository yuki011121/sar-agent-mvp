"""
Lost Person Behavior — Monte Carlo Simulation Engine.

Simulates a lost person's movement from the Last Known Position (LKP)
using behavioral profiles derived from ISRID/Koester research.

Six movement strategies are sampled at each step via the profile's PMF vector:
  RW = Random Walking     RT = Route Traveling    DT = Direction Traveling
  SP = Staying Put        VE = View Enhancing     BT = Backtracking

Aggregate 200-1000 runs to get an endpoint probability distribution.
"""

import numpy as np
import networkx as nx
from typing import Dict, List, Optional
from dataclasses import dataclass

from agents.path_analysis.lpt_profiles import (
    LPTProfile, RW, RT, DT, SP, VE, BT, STRATEGY_NAMES,
)


@dataclass
class AgentState:
    current_node: int
    previous_node: Optional[int]
    position: np.ndarray           # [x, y] projected coords (meters)
    previous_position: Optional[np.ndarray]
    velocity: np.ndarray           # [vx, vy]
    step_count: int
    trajectory: List[int]
    heading: float                 # radians


@dataclass
class SimulationResult:
    trajectory: List[int]
    endpoint: int
    steps_taken: int
    stop_reason: str               # "max_steps" | "boundary" | "stuck"


@dataclass
class MonteCarloResults:
    endpoint_counts: Dict[int, int]   # node_id -> runs ending here
    visit_counts: Dict[int, int]      # node_id -> runs passing through here
    total_runs: int
    all_trajectories: List[List[int]]
    all_endpoints: List[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_node_xy(graph: nx.Graph, node: int) -> np.ndarray:
    data = graph.nodes[node]
    if "proj_x" in data and "proj_y" in data:
        return np.array([data["proj_x"], data["proj_y"]], dtype=np.float64)
    return np.array([data["x"], data["y"]], dtype=np.float64)


def _get_neighbors(graph: nx.Graph, node: int) -> List[int]:
    if isinstance(graph, nx.DiGraph):
        neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
    else:
        neighbors = set(graph.neighbors(node))
    return list(neighbors)


def _get_node_elevation(graph: nx.Graph, node: int) -> float:
    data = graph.nodes[node]
    return float(data.get("elevation", data.get("ele", 0.0)))


def _get_edge_cost(graph: nx.Graph, from_node: int, to_node: int,
                   profile: LPTProfile) -> float:
    edge_data = graph.get_edge_data(from_node, to_node)
    if edge_data is None:
        edge_data = graph.get_edge_data(to_node, from_node)
    if edge_data is None:
        return 10.0

    if isinstance(edge_data, dict) and 0 in edge_data:
        edge_data = edge_data[0]

    base_length = float(edge_data.get("length", 100.0))
    weights = profile.terrain_weights
    cost = base_length

    highway = edge_data.get("highway", "")
    if highway:
        trail_factor = weights.get("trail_attraction", 1.0)
        cost /= max(trail_factor, 0.1)

    elev_from = _get_node_elevation(graph, from_node)
    elev_to = _get_node_elevation(graph, to_node)
    if base_length > 0:
        grade = abs(elev_to - elev_from) / base_length
        cost *= (1.0 + grade * weights.get("slope_penalty", 1.0) * 5.0)

    surface = edge_data.get("surface", "")
    if surface in ("grass", "ground", "dirt", "mud"):
        cost *= (1.0 + weights.get("brush_penalty", 1.0) * 0.3)

    return max(cost, 0.01)


def _normalize(vec: np.ndarray) -> np.ndarray:
    mag = np.linalg.norm(vec)
    if mag < 1e-10:
        return np.zeros_like(vec)
    return vec / mag


def _distance(pos1: np.ndarray, pos2: np.ndarray) -> float:
    return float(np.linalg.norm(pos2 - pos1))


# ---------------------------------------------------------------------------
# Core: apply_strategy
# ---------------------------------------------------------------------------

def apply_strategy(strategy: int, state: AgentState, graph: nx.Graph,
                   profile: LPTProfile, rng: np.random.Generator) -> Optional[int]:
    neighbors = _get_neighbors(graph, state.current_node)
    if not neighbors:
        return None

    # Avoid immediate oscillation (except Backtracking)
    if strategy != BT and state.previous_node is not None:
        forward = [n for n in neighbors if n != state.previous_node]
        if forward:
            neighbors = forward

    if strategy == RW:
        return int(rng.choice(neighbors))

    elif strategy == RT:
        trail_neighbors = []
        for n in neighbors:
            ed = graph.get_edge_data(state.current_node, n) or graph.get_edge_data(n, state.current_node)
            if ed is None:
                continue
            if isinstance(ed, dict) and 0 in ed:
                ed = ed[0]
            if ed.get("highway", ""):
                trail_neighbors.append(n)

        if not trail_neighbors:
            return int(rng.choice(neighbors))

        if np.linalg.norm(state.velocity) > 1e-10:
            best_node, best_align = None, -2.0
            for n in trail_neighbors:
                direction = _normalize(_get_node_xy(graph, n) - state.position)
                alignment = float(np.dot(direction, _normalize(state.velocity)))
                if alignment > best_align:
                    best_align = alignment
                    best_node = n
            if best_node is not None:
                return best_node

        return int(rng.choice(trail_neighbors))

    elif strategy == DT:
        if np.linalg.norm(state.velocity) < 1e-10:
            return int(rng.choice(neighbors))

        best_node, best_align = None, -2.0
        for n in neighbors:
            direction = _normalize(_get_node_xy(graph, n) - state.position)
            alignment = float(np.dot(direction, _normalize(state.velocity)))
            if alignment > best_align:
                best_align = alignment
                best_node = n
        return best_node if best_node is not None else int(rng.choice(neighbors))

    elif strategy == SP:
        return state.current_node

    elif strategy == VE:
        best_node, best_elev = None, -float("inf")
        for n in neighbors:
            elev = _get_node_elevation(graph, n)
            if elev > best_elev:
                best_elev = elev
                best_node = n
        if best_node is None or best_elev <= 0:
            return int(rng.choice(neighbors))
        return best_node

    elif strategy == BT:
        if len(state.trajectory) >= 2:
            for past_node in reversed(state.trajectory[:-1]):
                if past_node != state.current_node and past_node in neighbors:
                    return past_node
            if state.previous_node is not None and state.previous_node in neighbors:
                return state.previous_node
        return int(rng.choice(neighbors))

    else:
        raise ValueError(f"Unknown strategy index: {strategy}")


# ---------------------------------------------------------------------------
# Core: simulate_single_run
# ---------------------------------------------------------------------------

def simulate_single_run(
    graph: nx.Graph,
    lkp_node: int,
    profile: LPTProfile,
    max_steps: int = 500,
    boundary_radius_km: float = None,
    rng: np.random.Generator = None,
) -> SimulationResult:
    if rng is None:
        rng = np.random.default_rng()

    if boundary_radius_km is None:
        boundary_radius_km = profile.search_radius_km[3]  # 95th percentile

    boundary_radius_m = boundary_radius_km * 1000.0
    alpha = profile.alpha

    lkp_pos = _get_node_xy(graph, lkp_node)
    state = AgentState(
        current_node=lkp_node,
        previous_node=None,
        position=lkp_pos.copy(),
        previous_position=None,
        velocity=np.zeros(2, dtype=np.float64),
        step_count=0,
        trajectory=[lkp_node],
        heading=rng.uniform(0, 2 * np.pi),
    )

    # Initial step to establish velocity
    neighbors = _get_neighbors(graph, lkp_node)
    if not neighbors:
        return SimulationResult(trajectory=[lkp_node], endpoint=lkp_node,
                                steps_taken=0, stop_reason="stuck")

    first_neighbor = int(rng.choice(neighbors))
    first_pos = _get_node_xy(graph, first_neighbor)
    state.velocity = first_pos - lkp_pos
    state.previous_position = lkp_pos.copy()
    state.previous_node = lkp_node
    state.current_node = first_neighbor
    state.position = first_pos.copy()
    state.trajectory.append(first_neighbor)
    state.step_count = 1

    stop_reason = "max_steps"
    consecutive_stuck = 0

    for step in range(1, max_steps):
        strategy = profile.sample_strategy(rng)
        next_node = apply_strategy(strategy, state, graph, profile, rng)

        if next_node is None:
            consecutive_stuck += 1
            if consecutive_stuck >= 5:
                stop_reason = "stuck"
                break
            continue

        consecutive_stuck = 0
        next_pos = _get_node_xy(graph, next_node)

        if state.previous_position is not None and next_node != state.current_node:
            desired_velocity = next_pos - state.position
            state.velocity = alpha * desired_velocity + (1.0 - alpha) * state.velocity
        elif next_node != state.current_node:
            state.velocity = next_pos - state.position

        state.previous_position = state.position.copy()
        state.previous_node = state.current_node
        state.position = next_pos.copy()
        state.current_node = next_node
        state.step_count = step + 1
        state.trajectory.append(next_node)

        if np.linalg.norm(state.velocity) > 1e-10:
            state.heading = float(np.arctan2(state.velocity[1], state.velocity[0]))

        if _distance(lkp_pos, state.position) > boundary_radius_m:
            stop_reason = "boundary"
            break

    return SimulationResult(
        trajectory=state.trajectory,
        endpoint=state.current_node,
        steps_taken=state.step_count,
        stop_reason=stop_reason,
    )


# ---------------------------------------------------------------------------
# Core: run_monte_carlo
# ---------------------------------------------------------------------------

def run_monte_carlo(
    graph: nx.Graph,
    lkp_node: int,
    profile: LPTProfile,
    n_runs: int = 200,
    max_steps: int = 500,
    boundary_radius_km: float = None,
    seed: int = None,
    verbose: bool = False,
) -> MonteCarloResults:
    rng = np.random.default_rng(seed)

    endpoint_counts: Dict[int, int] = {}
    visit_counts: Dict[int, int] = {}
    all_trajectories: List[List[int]] = []
    all_endpoints: List[int] = []

    for i in range(n_runs):
        if verbose and (i + 1) % 50 == 0:
            print(f"  Monte Carlo run {i + 1}/{n_runs}...")

        child_rng = np.random.default_rng(rng.integers(0, 2**31))

        result = simulate_single_run(
            graph=graph,
            lkp_node=lkp_node,
            profile=profile,
            max_steps=max_steps,
            boundary_radius_km=boundary_radius_km,
            rng=child_rng,
        )

        ep = result.endpoint
        endpoint_counts[ep] = endpoint_counts.get(ep, 0) + 1
        all_endpoints.append(ep)

        for node in set(result.trajectory):
            visit_counts[node] = visit_counts.get(node, 0) + 1

        all_trajectories.append(result.trajectory)

    return MonteCarloResults(
        endpoint_counts=endpoint_counts,
        visit_counts=visit_counts,
        total_runs=n_runs,
        all_trajectories=all_trajectories,
        all_endpoints=all_endpoints,
    )


# ---------------------------------------------------------------------------
# Utility: snap lat/lon to nearest graph node
# ---------------------------------------------------------------------------

def snap_to_graph(graph: nx.Graph, lat: float, lon: float) -> int:
    min_dist = float("inf")
    nearest_node = None

    for node, data in graph.nodes(data=True):
        node_lat = data.get("y", 0)
        node_lon = data.get("x", 0)
        dist = (node_lat - lat) ** 2 + (node_lon - lon) ** 2
        if dist < min_dist:
            min_dist = dist
            nearest_node = node

    if nearest_node is None:
        raise ValueError("Graph has no nodes")
    return nearest_node
