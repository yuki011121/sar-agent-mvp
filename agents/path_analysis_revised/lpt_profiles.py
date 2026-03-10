LPT_PROFILES = {
    "dementia": {
        "pmf": {"RW": 0.30, "RT": 0.20, "DT": 0.25, "SP": 0.20, "VE": 0.00, "BT": 0.05},
        "downhill_bias": 0.1,
        "elevation_penalty": 0.1,
        "trail_attraction": 1.0,
        "road_attraction": 0.9,
        "brush_penalty": 1.2,
    },
    "child": {
        "pmf": {"RW": 0.50, "RT": 0.10, "DT": 0.10, "SP": 0.20, "VE": 0.05, "BT": 0.05},
        "downhill_bias": 0.1,
        "elevation_penalty": 0.2,
        "trail_attraction": 0.8,
        "road_attraction": 0.8,
        "brush_penalty": 1.5,
    },
    "hiker": {
        "pmf": {"RW": 0.10, "RT": 0.45, "DT": 0.20, "SP": 0.05, "VE": 0.10, "BT": 0.10},
        "downhill_bias": 0.3,
        "elevation_penalty": 0.3,
        "trail_attraction": 0.6,
        "road_attraction": 1.0,
        "brush_penalty": 1.8,
    },
    "despondent": {
        "pmf": {"RW": 0.20, "RT": 0.15, "DT": 0.20, "SP": 0.35, "VE": 0.05, "BT": 0.05},
        "downhill_bias": 0.2,
        "elevation_penalty": 0.2,
        "trail_attraction": 1.0,
        "road_attraction": 0.8,
        "brush_penalty": 1.3,
    },
}