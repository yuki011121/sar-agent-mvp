"""
Lost Person Type (LPT) Profiles — Derived from Koester's Lost Person Behavior & ISRID Data.

Each profile has a PMF vector [RW, RT, DT, SP, VE, BT] summing to 1.0:
  RW = Random Walking     RT = Route Traveling    DT = Direction Traveling
  SP = Staying Put        VE = View Enhancing     BT = Backtracking

Sources:
  - Koester, R.J. "Lost Person Behavior" (2008)
  - Hashimoto et al. (2022) validated hiker profiles
  - ISRID published distance/behavior statistics
"""

from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np


@dataclass
class LPTProfile:
    name: str
    description: str
    pmf_vector: List[float]   # [RW, RT, DT, SP, VE, BT]
    alpha: float              # velocity smoothing: higher = more momentum
    terrain_weights: Dict[str, float] = field(default_factory=dict)
    search_radius_km: List[float] = field(default_factory=list)  # [25th,50th,75th,95th]
    mobility_kmh: float = 1.0
    mobility_hours: float = 8.0

    def __post_init__(self):
        total = sum(self.pmf_vector)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"PMF vector for '{self.name}' sums to {total}, must sum to 1.0")

    def sample_strategy(self, rng: np.random.Generator = None) -> int:
        if rng is None:
            rng = np.random.default_rng()
        return int(rng.choice(6, p=self.pmf_vector))

    def get_max_steps(self, step_distance_km: float = 0.01) -> int:
        total_distance = self.mobility_kmh * self.mobility_hours
        return int(total_distance / step_distance_km)


RW = 0  # Random Walking
RT = 1  # Route Traveling
DT = 2  # Direction Traveling
SP = 3  # Staying Put
VE = 4  # View Enhancing
BT = 5  # Backtracking

STRATEGY_NAMES = [
    "Random Walking", "Route Traveling", "Direction Traveling",
    "Staying Put", "View Enhancing", "Backtracking",
]


LPT_PROFILES: Dict[str, LPTProfile] = {

    "young_child": LPTProfile(
        name="Young Child (1-6 years)",
        description="Very short range, random movement, high stay-put rate, no navigation ability",
        pmf_vector=[0.30, 0.05, 0.00, 0.55, 0.00, 0.10],
        alpha=0.30,
        terrain_weights={
            "trail_attraction": 0.2,
            "brush_penalty": 2.5,
            "slope_penalty": 2.0,
            "water_attraction": 1.5,
            "road_attraction": 0.3,
            "shelter_attraction": 1.0,
        },
        search_radius_km=[0.2, 0.4, 0.8, 2.0],
        mobility_kmh=0.5,
        mobility_hours=3.0,
    ),

    "older_child": LPTProfile(
        name="Older Child (7-12 years)",
        description="Moderate range, some trail awareness, may attempt to self-rescue",
        pmf_vector=[0.20, 0.25, 0.10, 0.25, 0.05, 0.15],
        alpha=0.40,
        terrain_weights={
            "trail_attraction": 0.8,
            "brush_penalty": 1.8,
            "slope_penalty": 1.5,
            "water_attraction": 1.2,
            "road_attraction": 0.8,
            "shelter_attraction": 1.2,
        },
        search_radius_km=[0.4, 1.0, 2.0, 4.0],
        mobility_kmh=1.5,
        mobility_hours=5.0,
    ),

    "active_adult": LPTProfile(
        name="Active Adult / Hiker",
        description="High mobility, strong trail following, goal-directed, may seek viewpoints",
        # Hashimoto et al. (2022) best-fit validated against real hiker cases
        pmf_vector=[0.03, 0.50, 0.17, 0.05, 0.08, 0.17],
        alpha=0.55,
        terrain_weights={
            "trail_attraction": 2.0,
            "brush_penalty": 1.2,
            "slope_penalty": 0.8,
            "water_attraction": 1.0,
            "road_attraction": 1.5,
            "shelter_attraction": 0.5,
        },
        search_radius_km=[1.0, 2.0, 4.0, 10.0],
        mobility_kmh=3.5,
        mobility_hours=10.0,
    ),

    "impaired": LPTProfile(
        name="Impaired (Dementia / Alzheimer's / Intoxicated)",
        description="Short range, highly random, no navigation strategy, drawn to water hazards",
        pmf_vector=[0.45, 0.10, 0.05, 0.30, 0.00, 0.10],
        alpha=0.25,
        terrain_weights={
            "trail_attraction": 0.5,
            "brush_penalty": 2.0,
            "slope_penalty": 2.0,
            "water_attraction": 2.5,  # Koester: water hazard is primary mortality factor
            "road_attraction": 0.8,
            "shelter_attraction": 1.5,
        },
        search_radius_km=[0.2, 0.7, 1.5, 3.5],
        mobility_kmh=1.0,
        mobility_hours=6.0,
    ),

    "despondent": LPTProfile(
        name="Despondent",
        description="Purposeful travel to isolated or hazardous locations, avoids people",
        pmf_vector=[0.10, 0.15, 0.35, 0.15, 0.05, 0.20],
        alpha=0.60,
        terrain_weights={
            "trail_attraction": 1.0,
            "brush_penalty": 0.5,
            "slope_penalty": 1.0,
            "water_attraction": 2.5,
            "road_attraction": 0.5,
            "shelter_attraction": 0.3,
        },
        search_radius_km=[0.3, 0.8, 2.0, 8.0],
        mobility_kmh=2.5,
        mobility_hours=4.0,
    ),

    "motorized_mounted": LPTProfile(
        name="Motorized / Mounted",
        description="Very high mobility, road and trail network dependent, large search area",
        pmf_vector=[0.02, 0.75, 0.10, 0.08, 0.00, 0.05],
        alpha=0.70,
        terrain_weights={
            "trail_attraction": 3.0,
            "brush_penalty": 3.0,
            "slope_penalty": 1.5,
            "water_attraction": 0.3,
            "road_attraction": 3.0,
            "shelter_attraction": 0.5,
        },
        search_radius_km=[3.0, 8.0, 15.0, 40.0],
        mobility_kmh=15.0,
        mobility_hours=6.0,
    ),
}

BEHAVIORAL_CLASS_NAMES = {
    0: "Young Child",
    1: "Older Child",
    2: "Active Adult",
    3: "Impaired",
    4: "Despondent",
    5: "Motorized/Mounted",
}


def get_profile(lpt_key: str) -> LPTProfile:
    if lpt_key not in LPT_PROFILES:
        raise KeyError(f"Unknown LPT key '{lpt_key}'. Valid: {list(LPT_PROFILES.keys())}")
    return LPT_PROFILES[lpt_key]
