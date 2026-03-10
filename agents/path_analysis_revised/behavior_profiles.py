BEHAVIOR_PROFILES = {
    "hiker": {
        "downhill_bias": 0.25,
        "trail_attraction": 0.65,
        "road_attraction": 0.80,
        "brush_penalty": 1.50,
        "elevation_penalty": 1.20,
    },
    "child": {
        "downhill_bias": 0.15,
        "trail_attraction": 0.50,
        "road_attraction": 0.60,
        "brush_penalty": 1.10,
        "elevation_penalty": 1.05,
    },
    "dementia": {
        "downhill_bias": 0.10,
        "trail_attraction": 0.45,
        "road_attraction": 0.55,
        "brush_penalty": 1.05,
        "elevation_penalty": 1.10,
    },
    "autistic": {
        "downhill_bias": 0.10,
        "trail_attraction": 0.60,
        "road_attraction": 0.65,
        "brush_penalty": 1.20,
        "elevation_penalty": 1.10,
    },
    "substance intoxication": {
        "downhill_bias": 0.35,
        "trail_attraction": 0.40,
        "road_attraction": 0.50,
        "brush_penalty": 1.05,
        "elevation_penalty": 1.05,
    },
    "atv": {
        "downhill_bias": 0.10,
        "trail_attraction": 0.75,
        "road_attraction": 0.50,
        "brush_penalty": 2.50,
        "elevation_penalty": 1.30,
    },
}

DEFAULT_PROFILE = {
    "downhill_bias": 0.20,
    "trail_attraction": 0.60,
    "road_attraction": 0.70,
    "brush_penalty": 1.30,
    "elevation_penalty": 1.15,
}