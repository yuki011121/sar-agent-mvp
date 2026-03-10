import numpy as np
import random
import networkx as nx
from lpt_profiles import LPT_PROFILES

def get_direction_vector(G, from_node, to_node):
    x1, y1 = G.nodes[from_node]['x'], G.nodes[from_node]['y']
    x2, y2 = G.nodes[to_node]['x'], G.nodes[to_node]['y']
    vec = np.array([x2 - x1, y2 - y1], dtype=float)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec

def apply_strategy(strategy, pos, prev_pos, G, velocity, trajectory):
    neighbors = list(G.neighbors(pos))
    if not neighbors:
        return pos

    if strategy == "SP":
        return pos

    elif strategy == "RW":
        # weighted random — uses your existing edge costs
        costs = []
        for n in neighbors:
            edge_data = min(G[pos][n].values(), 
                          key=lambda d: d.get("cost", 1.0))
            costs.append(1.0 / max(edge_data.get("cost", 1.0), 0.01))
        total = sum(costs)
        weights = [c/total for c in costs]
        return random.choices(neighbors, weights=weights)[0]

    elif strategy == "RT":
        trail_types = ["footway", "path", "track", "bridleway"]
        trail_neighbors = []
        for n in neighbors:
            edge_data = min(G[pos][n].values(), 
                          key=lambda d: d.get("cost", 1.0))
            if edge_data.get("highway", "") in trail_types:
                trail_neighbors.append(n)
        return random.choice(trail_neighbors) if trail_neighbors \
               else random.choice(neighbors)

    elif strategy == "DT":
        # continue in current velocity direction
        pos_xy = np.array([G.nodes[pos]['x'], G.nodes[pos]['y']])
        best, best_score = None, -np.inf
        for n in neighbors:
            n_xy = np.array([G.nodes[n]['x'], G.nodes[n]['y']])
            direction = n_xy - pos_xy
            norm = np.linalg.norm(direction)
            if norm > 0:
                direction = direction / norm
            score = np.dot(direction, velocity)
            if score > best_score:
                best_score = score
                best = n
        return best if best else random.choice(neighbors)

    elif strategy == "VE":
        # move to highest elevation neighbor
        elevations = [G.nodes[n].get("elevation", 0) for n in neighbors]
        return neighbors[np.argmax(elevations)]

    elif strategy == "BT":
        # walk back along trajectory
        if len(trajectory) >= 2:
            target = trajectory[-2]
            if target in neighbors:
                return target
        return random.choice(neighbors)

    return random.choice(neighbors)


def simulate_single_run(G, lkp_node, lpt_profile, steps=200, alpha=0.7):
    pmf = lpt_profile["pmf"]
    strategies = list(pmf.keys())
    weights = list(pmf.values())

    neighbors = list(G.neighbors(lkp_node))
    if not neighbors:
        return [lkp_node]

    prev_pos = random.choice(neighbors)
    pos = lkp_node
    velocity = get_direction_vector(G, prev_pos, pos)
    trajectory = [prev_pos, pos]

    for _ in range(steps):
        strategy = random.choices(strategies, weights=weights)[0]
        next_pos = apply_strategy(
            strategy, pos, prev_pos, G, velocity, trajectory
        )

        new_dir = get_direction_vector(G, pos, next_pos)
        velocity = alpha * velocity + (1 - alpha) * new_dir
        norm = np.linalg.norm(velocity)
        if norm > 0:
            velocity = velocity / norm

        trajectory.append(next_pos)
        prev_pos = pos
        pos = next_pos

    return trajectory


def run_monte_carlo(G, lkp_node, lpt_type: str, n_runs=10, steps=200, alpha=0.7):
    profile = LPT_PROFILES.get(lpt_type)
    if not profile:
        raise ValueError(f"Unknown LPT type: {lpt_type}")

    all_trajectories = []
    endpoint_counts = {}
    node_visit_counts = {}

    for _ in range(n_runs):
        traj = simulate_single_run(G, lkp_node, profile, steps, alpha)
        all_trajectories.append(traj)

        # count endpoints
        endpoint = traj[-1]
        endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

        # count all visited nodes (for heatmap density)
        for node in set(traj):
            node_visit_counts[node] = node_visit_counts.get(node, 0) + 1

    return {
        "trajectories": all_trajectories,
        "endpoint_counts": endpoint_counts,
        "node_visit_counts": node_visit_counts,
        "n_runs": n_runs,
    }