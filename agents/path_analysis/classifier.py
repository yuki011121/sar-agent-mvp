"""
Rule-based Lost Person Type (LPT) classifier.

Maps observable person attributes (age, cognitive state, physical condition)
to an LPT profile key using thresholds derived from ISRID/Koester statistics.

No ML needed: the discriminating features (distance traveled, dispersion angle)
are unknowable at search start, so a lookup table on age + cognitive state
performs equivalently to a trained classifier.
"""

from typing import Tuple
from agents.path_analysis.lpt_profiles import LPTProfile, get_profile


def classify_person(
    age: int,
    cognitive_state: float = 0.9,   # 0.0 = severely impaired, 1.0 = fully alert
    physical_condition: float = 0.8, # 0.0 = poor, 1.0 = excellent
    has_vehicle: bool = False,
) -> Tuple[str, LPTProfile]:
    """
    Classify a missing person into an LPT category and return their profile.

    Args:
        age: Person's age in years
        cognitive_state: Cognitive alertness (0=impaired, 1=alert)
        physical_condition: Physical fitness (0=poor, 1=excellent)
        has_vehicle: Whether the person may be motorized/mounted

    Returns:
        (lpt_key, LPTProfile) — e.g. ("impaired", <LPTProfile>)
    """
    if has_vehicle:
        key = "motorized_mounted"
    elif age <= 6:
        key = "young_child"
    elif age <= 12:
        key = "older_child"
    elif cognitive_state < 0.35:
        # Low cognitive: dementia, autism, severe intoxication
        key = "impaired"
    elif cognitive_state < 0.60 and physical_condition < 0.50:
        # Moderate cognitive impairment + poor physical → despondent-type behavior
        key = "despondent"
    else:
        key = "active_adult"

    return key, get_profile(key)


def parse_person_info(payload: dict) -> dict:
    """
    Extract and validate person classification parameters from a Redis payload.
    Returns defaults for missing fields so the classifier always runs.
    """
    person = payload.get("person", {}) or {}
    return {
        "age": int(person.get("age", 35)),
        "cognitive_state": float(person.get("cognitive_state", 0.9)),
        "physical_condition": float(person.get("physical_condition", 0.8)),
        "has_vehicle": bool(person.get("has_vehicle", False)),
    }
