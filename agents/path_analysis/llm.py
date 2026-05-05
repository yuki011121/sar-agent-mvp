import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("path-analysis-agent")

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
MODEL_NAME = os.getenv("GEN_TEXT_MODEL", "gemini-2.5-flash")

_model = None

def _get_model():
    global _model
    if _model is None:
        if not api_key:
            return None
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel(MODEL_NAME)
    return _model


def summarize_results(
    person_class: str,
    profile,          # LPTProfile
    top_points: list, # from get_top_points()
    lkp_lat: float,
    lkp_lon: float,
) -> str:
    """
    Generate a plain-English SAR field briefing from Monte Carlo results.
    Falls back to a structured text summary if the LLM is unavailable.
    """
    fallback = (
        f"Missing person classified as {profile.name}. "
        f"Primary search radius: {profile.search_radius_km[2]} km (75th percentile), "
        f"maximum {profile.search_radius_km[3]} km (95th percentile). "
        f"Highest probability area: {top_points[0]['endpoint_probability']:.1%} endpoint "
        f"probability at ({top_points[0]['lat']:.5f}, {top_points[0]['lon']:.5f})."
        if top_points else
        f"Missing person classified as {profile.name}. No high-probability locations identified."
    )

    model = _get_model()
    if model is None:
        return fallback

    # Give LLM only top-5 points to keep prompt tight
    top5 = top_points[:5]
    # Describe relative positions (bearing + approx distance from LKP)
    point_descriptions = []
    for p in top5:
        dlat = p["lat"] - lkp_lat
        dlon = p["lon"] - lkp_lon
        dist_km = ((dlat * 111) ** 2 + (dlon * 111) ** 2) ** 0.5
        bearing = "N" if dlat > 0 else "S"
        bearing += "E" if dlon > 0 else "W"
        point_descriptions.append(
            f"  - Rank {p['rank']}: {dist_km:.2f} km {bearing} of LKP "
            f"({p['endpoint_probability']:.1%} endpoint probability)"
        )

    prompt = f"""You are a Search and Rescue (SAR) coordinator assistant.

Missing person profile:
  Type: {profile.name}
  Behavior: {profile.description}
  Search radius: 50th percentile = {profile.search_radius_km[1]} km, 75th = {profile.search_radius_km[2]} km, 95th = {profile.search_radius_km[3]} km

Monte Carlo simulation ({len(top_points)} high-probability locations identified).
Top 5 most likely endpoints relative to Last Known Position:
{chr(10).join(point_descriptions)}

Write a concise SAR field briefing in 3-4 sentences:
1. Describe this person type and their expected movement behavior.
2. State the recommended primary search radius (75th percentile) and maximum (95th percentile).
3. Describe where the highest-probability areas are (direction and approximate distance from LKP).
4. Give one tactical recommendation for search teams.

Do NOT quote raw coordinates or probability numbers. Write in plain English for field personnel."""

    try:
        response = model.generate_content(prompt)
        text = (getattr(response, "text", None) or "").strip()
        return text if text else fallback
    except Exception as e:
        logger.warning(f"LLM summary failed: {e}. Using fallback.")
        return fallback
