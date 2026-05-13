"""
SAR Verification Layer — MAKE2026 Integration for ClueMeister Agent

Self-contained module: all MAKE2026 classes copied inline so the cluemeister
container does not need to include the MAKE2026/src package.

Core classes copied from agents/MAKE2026/src/:
  - ProbabilityKG         (kg/probability_kg.py)
  - KGGrounding           (verification/grounding.py)
  - ContradictionDetector (verification/contradiction.py)
  - DecisionMaker         (verification/decision.py)
  - AgentClaim, ClaimType (agents/claim_extractor.py)
  - GroundingResult, HopType, ContradictionResult, ContradictionType,
    Decision, DecisionTier  (respective verification modules)

New class:
  - SARVerificationEngine — bridges free-form agent text → MAKE2026 pipeline
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (from MAKE2026/src/config.py)
# ---------------------------------------------------------------------------
LOW_PROBABILITY_THRESHOLD     = 0.15
CONFIDENCE_MISMATCH_THRESHOLD = 0.40
ACCEPT_THRESHOLD              = 0.70
FLAG_THRESHOLD                = 0.50
CANDIDATE_THRESHOLD           = 0.30
REJECT_SEVERITY               = 0.70
MIN_SAMPLES_FOR_PROBABILITY   = 30


# ===========================================================================
# Data structures (from MAKE2026/src/agents/claim_extractor.py)
# ===========================================================================

class ClaimType(Enum):
    TERRAIN  = "terrain"
    STATUS   = "status"
    COMBINED = "combined"


@dataclass
class AgentClaim:
    claim_id:       str
    source_agent:   str
    claim_type:     ClaimType
    scenario_id:    str
    subject_type:   str
    scenario_type:  Optional[str]
    predicted_value: str
    confidence:     float
    reasoning:      str
    raw_response:   Optional[str] = None

    def __post_init__(self):
        self.confidence     = max(0.0, min(1.0, self.confidence))
        self.predicted_value = str(self.predicted_value).lower()
        self.subject_type   = str(self.subject_type).lower()
        if self.scenario_type:
            self.scenario_type = str(self.scenario_type).lower()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["claim_type"] = self.claim_type.value
        return d

    def get_kg_key(self):
        if self.scenario_type:
            return (self.subject_type, self.scenario_type)
        return self.subject_type


# ===========================================================================
# ProbabilityKG (from MAKE2026/src/kg/probability_kg.py)
# ===========================================================================

class ProbabilityKG:
    def __init__(self, df: pd.DataFrame = None, min_samples: int = None):
        self.min_samples = min_samples or MIN_SAMPLES_FOR_PROBABILITY
        self.prob_tables:   Dict[str, Dict] = {}
        self.sample_counts: Dict[str, Dict] = {}
        self.metadata:      Dict[str, Any]  = {}
        if df is not None:
            self._build_all_tables(df)

    def _build_all_tables(self, df: pd.DataFrame) -> None:
        self.prob_tables["terrain_given_subject"], self.sample_counts["terrain_given_subject"] = \
            self._build_conditional_table(df, "Subject.Category.Clean", "Terrain.Clean")
        self.prob_tables["status_given_subject"], self.sample_counts["status_given_subject"] = \
            self._build_conditional_table(df, "Subject.Category.Clean", "Subject.Status.Clean")
        if "Scenario.Clean" in df.columns:
            self.prob_tables["status_given_subject_scenario"], \
            self.sample_counts["status_given_subject_scenario"] = \
                self._build_two_hop_table(df, "Subject.Category.Clean", "Scenario.Clean", "Subject.Status.Clean")
        self.metadata = {
            "total_records": len(df),
            "min_samples": self.min_samples,
            "tables": list(self.prob_tables.keys()),
        }

    def _build_conditional_table(self, df, condition_col, target_col):
        valid = df.dropna(subset=[condition_col, target_col])
        crosstab = pd.crosstab(valid[condition_col], valid[target_col], normalize="index")
        counts   = valid.groupby(condition_col).size()
        prob_dict, count_dict = {}, {}
        for condition in crosstab.index:
            n = counts.get(condition, 0)
            if n >= self.min_samples:
                k = str(condition).lower()
                prob_dict[k]  = {str(c).lower(): float(v)
                                  for c, v in crosstab.loc[condition].to_dict().items() if v > 0}
                count_dict[k] = int(n)
        return prob_dict, count_dict

    def _build_two_hop_table(self, df, col1, col2, target_col):
        valid = df.dropna(subset=[col1, col2, target_col])
        prob_dict, count_dict = {}, {}
        for (c1, c2), group in valid.groupby([col1, col2]):
            if len(group) >= self.min_samples:
                dist = group[target_col].value_counts(normalize=True)
                key = (str(c1).lower(), str(c2).lower())
                prob_dict[key]  = {str(k).lower(): float(v)
                                    for k, v in dist.to_dict().items() if v > 0}
                count_dict[key] = len(group)
        return prob_dict, count_dict

    def get_probability(self, table_name: str, key, target: str) -> Optional[float]:
        table  = self.prob_tables.get(table_name, {})
        key    = tuple(str(k).lower() for k in key) if isinstance(key, tuple) else str(key).lower()
        target = str(target).lower()
        return table.get(key, {}).get(target, None)

    def get_distribution(self, table_name: str, key) -> Dict[str, float]:
        table = self.prob_tables.get(table_name, {})
        key   = tuple(str(k).lower() for k in key) if isinstance(key, tuple) else str(key).lower()
        return table.get(key, {})

    def get_most_likely(self, table_name: str, key) -> Tuple[Optional[str], float]:
        dist = self.get_distribution(table_name, key)
        if not dist:
            return (None, 0.0)
        return max(dist.items(), key=lambda x: x[1])

    def get_sample_count(self, table_name: str, key) -> int:
        counts = self.sample_counts.get(table_name, {})
        key    = tuple(str(k).lower() for k in key) if isinstance(key, tuple) else str(key).lower()
        return counts.get(key, 0)

    def has_key(self, table_name: str, key) -> bool:
        table = self.prob_tables.get(table_name, {})
        key   = tuple(str(k).lower() for k in key) if isinstance(key, tuple) else str(key).lower()
        return key in table

    def save(self, filepath: Path) -> None:
        serializable: Dict[str, Any] = {"prob_tables": {}, "sample_counts": {}, "metadata": self.metadata}
        for table_name, table in self.prob_tables.items():
            if "subject_scenario" in table_name:
                serializable["prob_tables"][table_name]  = {f"{k[0]}|{k[1]}": v for k, v in table.items()}
                serializable["sample_counts"][table_name] = {f"{k[0]}|{k[1]}": v
                                                              for k, v in self.sample_counts[table_name].items()}
            else:
                serializable["prob_tables"][table_name]  = table
                serializable["sample_counts"][table_name] = self.sample_counts[table_name]
        with open(filepath, "w") as f:
            json.dump(serializable, f, indent=2)

    @classmethod
    def load(cls, filepath: Path) -> "ProbabilityKG":
        with open(filepath, "r") as f:
            data = json.load(f)
        kg = cls()
        kg.metadata    = data.get("metadata", {})
        kg.min_samples = kg.metadata.get("min_samples", MIN_SAMPLES_FOR_PROBABILITY)
        for table_name, table in data["prob_tables"].items():
            if "subject_scenario" in table_name:
                kg.prob_tables[table_name]  = {tuple(k.split("|")): v for k, v in table.items()}
                kg.sample_counts[table_name] = {tuple(k.split("|")): v
                                                 for k, v in data["sample_counts"][table_name].items()}
            else:
                kg.prob_tables[table_name]  = table
                kg.sample_counts[table_name] = data["sample_counts"][table_name]
        logger.info(f"Loaded ProbabilityKG from {filepath} — tables: {list(kg.prob_tables.keys())}")
        return kg


# ===========================================================================
# KGGrounding (from MAKE2026/src/verification/grounding.py)
# ===========================================================================

class HopType(Enum):
    SINGLE = "single"
    TWO    = "two"
    NONE   = "none"


@dataclass
class GroundingResult:
    claim_id:             str
    is_grounded:          bool
    kg_probability:       Optional[float]
    stated_confidence:    float
    grounding_confidence: float
    hop_type:             HopType
    sample_count:         int
    kg_distribution:      Dict[str, float]
    evidence:             Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hop_type"] = self.hop_type.value
        return d


class KGGrounding:
    def __init__(self, prob_kg: ProbabilityKG):
        self.kg = prob_kg

    def ground_claim(self, claim: AgentClaim) -> GroundingResult:
        if claim.claim_type == ClaimType.TERRAIN:
            return self._ground_terrain_claim(claim)
        elif claim.claim_type == ClaimType.STATUS:
            return self._ground_status_claim(claim)
        return GroundingResult(claim.claim_id, False, None, claim.confidence,
                               claim.confidence * 0.3, HopType.NONE, 0, {}, {"error": "Unknown claim type"})

    def _ground_terrain_claim(self, claim: AgentClaim) -> GroundingResult:
        table     = "terrain_given_subject"
        kg_prob   = self.kg.get_probability(table, claim.subject_type, claim.predicted_value)
        kg_dist   = self.kg.get_distribution(table, claim.subject_type)
        n_samples = self.kg.get_sample_count(table, claim.subject_type)
        grounded  = kg_prob is not None and kg_prob > 0.01
        g_conf    = self._calc_grounding_conf(claim.confidence, kg_prob, grounded)
        return GroundingResult(claim.claim_id, grounded, kg_prob, claim.confidence, g_conf,
                               HopType.SINGLE if grounded else HopType.NONE, n_samples, kg_dist,
                               {"table": table, "key": claim.subject_type,
                                "predicted": claim.predicted_value,
                                "most_likely": self.kg.get_most_likely(table, claim.subject_type)})

    def _ground_status_claim(self, claim: AgentClaim) -> GroundingResult:
        if claim.scenario_type:
            result = self._try_two_hop(claim)
            if result.is_grounded:
                return result
        return self._single_hop_status(claim)

    def _try_two_hop(self, claim: AgentClaim) -> GroundingResult:
        table  = "status_given_subject_scenario"
        key    = (claim.subject_type, claim.scenario_type)
        kg_prob   = self.kg.get_probability(table, key, claim.predicted_value)
        kg_dist   = self.kg.get_distribution(table, key)
        n_samples = self.kg.get_sample_count(table, key)
        if not kg_dist:
            return GroundingResult(claim.claim_id, False, None, claim.confidence,
                                   claim.confidence * 0.5, HopType.NONE, 0, {},
                                   {"table": table, "key": str(key), "reason": "No two-hop data"})
        grounded = kg_prob is not None and kg_prob > 0.01
        g_conf   = self._calc_grounding_conf(claim.confidence, kg_prob, grounded)
        return GroundingResult(claim.claim_id, grounded, kg_prob, claim.confidence, g_conf,
                               HopType.TWO if grounded else HopType.NONE, n_samples, kg_dist,
                               {"table": table, "key": str(key), "predicted": claim.predicted_value,
                                "most_likely": self.kg.get_most_likely(table, key)})

    def _single_hop_status(self, claim: AgentClaim) -> GroundingResult:
        table     = "status_given_subject"
        kg_prob   = self.kg.get_probability(table, claim.subject_type, claim.predicted_value)
        kg_dist   = self.kg.get_distribution(table, claim.subject_type)
        n_samples = self.kg.get_sample_count(table, claim.subject_type)
        grounded  = kg_prob is not None and kg_prob > 0.01
        g_conf    = self._calc_grounding_conf(claim.confidence, kg_prob, grounded)
        return GroundingResult(claim.claim_id, grounded, kg_prob, claim.confidence, g_conf,
                               HopType.SINGLE if grounded else HopType.NONE, n_samples, kg_dist,
                               {"table": table, "key": claim.subject_type,
                                "predicted": claim.predicted_value,
                                "most_likely": self.kg.get_most_likely(table, claim.subject_type)})

    def _calc_grounding_conf(self, stated: float, kg_prob: Optional[float], grounded: bool) -> float:
        if not grounded or kg_prob is None:
            return stated * 0.3
        if kg_prob >= 0.5:
            return stated * 1.0
        if kg_prob >= 0.3:
            return stated * 0.9
        if kg_prob >= 0.1:
            return stated * 0.7
        return stated * 0.5

    def ground_claims(self, claims: List[AgentClaim]) -> List[GroundingResult]:
        return [self.ground_claim(c) for c in claims]


# ===========================================================================
# ContradictionDetector (from MAKE2026/src/verification/contradiction.py)
# ===========================================================================

class ContradictionType(Enum):
    NONE          = "none"
    LOW_PROBABILITY = "low_probability"
    OVERCONFIDENT = "overconfident"
    UNDERCONFIDENT = "underconfident"


@dataclass
class ContradictionResult:
    claim_id:          str
    has_contradiction: bool
    contradiction_type: ContradictionType
    severity:          float
    explanation:       str
    details:           Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["contradiction_type"] = self.contradiction_type.value
        return d


class ContradictionDetector:
    def __init__(self, low_prob_threshold: float = None, mismatch_threshold: float = None):
        self.low_prob_threshold  = low_prob_threshold  or LOW_PROBABILITY_THRESHOLD
        self.mismatch_threshold  = mismatch_threshold  or CONFIDENCE_MISMATCH_THRESHOLD

    def detect(self, claim: AgentClaim, grounding: GroundingResult) -> ContradictionResult:
        kg_prob    = grounding.kg_probability or 0.0
        stated     = claim.confidence
        conf_diff  = stated - kg_prob

        if kg_prob < self.low_prob_threshold:
            sev = max(0.0, min(1.0, 1.0 - kg_prob / self.low_prob_threshold))
            return ContradictionResult(
                claim.claim_id, True, ContradictionType.LOW_PROBABILITY, sev,
                f"KG shows only {kg_prob:.1%} probability for '{claim.predicted_value}'",
                {"kg_probability": kg_prob, "stated_confidence": stated,
                 "threshold": self.low_prob_threshold,
                 "most_likely": grounding.evidence.get("most_likely")})

        if conf_diff > self.mismatch_threshold:
            max_diff = 1.0 - self.mismatch_threshold
            sev = max(0.0, min(1.0, (abs(conf_diff) - self.mismatch_threshold) / max_diff if max_diff > 0 else 0))
            return ContradictionResult(
                claim.claim_id, True, ContradictionType.OVERCONFIDENT, sev,
                f"Agent claims {stated:.1%} confidence but KG shows only {kg_prob:.1%}",
                {"kg_probability": kg_prob, "stated_confidence": stated, "difference": conf_diff,
                 "threshold": self.mismatch_threshold})

        if kg_prob > 0.5 and -conf_diff > self.mismatch_threshold:
            max_diff = 1.0 - self.mismatch_threshold
            sev = max(0.0, min(1.0, (abs(conf_diff) - self.mismatch_threshold) / max_diff if max_diff > 0 else 0)) * 0.5
            return ContradictionResult(
                claim.claim_id, True, ContradictionType.UNDERCONFIDENT, sev,
                f"Agent claims only {stated:.1%} but KG shows {kg_prob:.1%}",
                {"kg_probability": kg_prob, "stated_confidence": stated, "difference": conf_diff})

        return ContradictionResult(
            claim.claim_id, False, ContradictionType.NONE, 0.0,
            "Claim is consistent with KG evidence",
            {"kg_probability": kg_prob, "stated_confidence": stated, "difference": conf_diff})

    def detect_all(self, claims: List[AgentClaim],
                   groundings: List[GroundingResult]) -> List[ContradictionResult]:
        return [self.detect(c, g) for c, g in zip(claims, groundings)]


# ===========================================================================
# DecisionMaker (from MAKE2026/src/verification/decision.py)
# ===========================================================================

class DecisionTier(Enum):
    ACCEPT      = "accept"
    FLAG        = "flag"
    CANDIDATE   = "candidate"
    REJECT      = "reject"
    CONFLICT    = "conflict"    # KG actively contradicts (≠ just low probability)
    UNVERIFIED  = "unverified"  # KG has no data for this claim type


@dataclass
class Decision:
    claim_id:         str
    tier:             DecisionTier
    final_confidence: float
    recommendation:   str
    evidence_summary: str
    factors:          Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value
        return d


class DecisionMaker:
    def __init__(self, accept_threshold=None, flag_threshold=None,
                 candidate_threshold=None, reject_severity=None):
        self.accept_threshold    = accept_threshold    or ACCEPT_THRESHOLD
        self.flag_threshold      = flag_threshold      or FLAG_THRESHOLD
        self.candidate_threshold = candidate_threshold or CANDIDATE_THRESHOLD
        self.reject_severity     = reject_severity     or REJECT_SEVERITY

    def decide(self, grounding: GroundingResult, contradiction: ContradictionResult) -> Decision:
        conf    = grounding.grounding_confidence
        sev     = contradiction.severity
        has_con = contradiction.has_contradiction
        adj     = conf * (1 - sev * 0.5) if has_con else conf

        # KG has no data at all — cannot verify, not a contradiction
        if not grounding.is_grounded and grounding.kg_probability is None:
            return Decision(grounding.claim_id, DecisionTier.UNVERIFIED, conf,
                            "Unverified: No ISRID data for this claim type",
                            "KG has no historical data to verify this claim",
                            {"grounding_confidence": conf, "kg_probability": None,
                             "hop_type": grounding.hop_type.value})

        # KG actively contradicts (high severity) — distinct from merely low probability
        if has_con and sev >= self.reject_severity:
            return Decision(grounding.claim_id, DecisionTier.CONFLICT, adj,
                            "Conflict: Contradicts historical data",
                            contradiction.explanation,
                            {"contradiction_severity": sev,
                             "contradiction_type": contradiction.contradiction_type.value,
                             "grounding_confidence": conf, "kg_probability": grounding.kg_probability})

        if adj >= self.accept_threshold:
            return Decision(grounding.claim_id, DecisionTier.ACCEPT, adj,
                            "Accept: Consistent with historical patterns",
                            f"KG probability: {grounding.kg_probability:.1%}" if grounding.kg_probability else "Grounded in KG",
                            {"grounding_confidence": conf, "adjusted_confidence": adj,
                             "kg_probability": grounding.kg_probability, "hop_type": grounding.hop_type.value})

        if adj >= self.flag_threshold:
            rec = "Flag for review: Moderate confidence"
            if has_con:
                rec += f" ({contradiction.contradiction_type.value})"
            return Decision(grounding.claim_id, DecisionTier.FLAG, adj, rec,
                            f"KG probability: {grounding.kg_probability:.1%}, Confidence: {adj:.1%}"
                            if grounding.kg_probability else f"Confidence: {adj:.1%}",
                            {"grounding_confidence": conf, "adjusted_confidence": adj,
                             "kg_probability": grounding.kg_probability, "has_contradiction": has_con})

        if adj >= self.candidate_threshold:
            return Decision(grounding.claim_id, DecisionTier.CANDIDATE, adj,
                            "Candidate: Requires expert verification",
                            f"Low confidence ({adj:.1%}), needs human review",
                            {"grounding_confidence": conf, "adjusted_confidence": adj,
                             "kg_probability": grounding.kg_probability})

        return Decision(grounding.claim_id, DecisionTier.REJECT, adj,
                        "Reject: Insufficient evidence",
                        f"Confidence too low ({adj:.1%})",
                        {"grounding_confidence": conf, "adjusted_confidence": adj,
                         "kg_probability": grounding.kg_probability})

    def decide_all(self, groundings: List[GroundingResult],
                   contradictions: List[ContradictionResult]) -> List[Decision]:
        return [self.decide(g, c) for g, c in zip(groundings, contradictions)]


# ===========================================================================
# Gemini claim extraction prompt
# ===========================================================================

CLAIM_EXTRACTION_PROMPT = """\
You are analyzing SAR (Search and Rescue) agent output text.
Extract structured claims the agent makes about the search subject's terrain or status.

Agent name: {agent_name}
Agent output (first 2000 chars):
{agent_text}

Extract claims about:
1. Terrain type: mountainous / flat / water / cave
2. Subject status: well / injured / deceased / missing

Return ONLY valid JSON — no markdown, no explanation:
{{"claims": [
  {{
    "claim_type": "terrain" or "status",
    "subject_type": "the SAR subject type in lowercase (e.g. hiker, dementia, child, climber, hunter)",
    "scenario_type": "scenario if mentioned (lost/overdue/injured/separated) or null",
    "predicted_value": "predicted terrain or status in lowercase",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief quote or paraphrase of agent reasoning (max 150 chars)"
  }}
]}}

Rules:
- Only include claims explicitly stated or strongly implied
- Map synonyms: alpine/mountain/peak/ridge → mountainous; river/lake/ocean/stream → water
- Map synonyms: alive/safe/rescued/found → well; hurt/wounded/trauma → injured; dead/body → deceased
- If no terrain or status claims exist, return {{"claims": []}}
- subject_type and predicted_value must be lowercase
"""


# ===========================================================================
# SARVerificationEngine — new adapter class
# ===========================================================================

class SARVerificationEngine:
    """
    Bridges the MAKE2026 verification pipeline to ClueMeister's free-form
    agent output text.

    On init:
      - Loads ProbabilityKG from bundled probability_kg.json
      - Instantiates KGGrounding, ContradictionDetector, DecisionMaker

    On verify_session():
      - Extracts AgentClaims from raw text via Gemini (falls back to heuristics)
      - Runs grounding → contradiction → decision
      - Returns a structured report dict
    """

    KG_PATH = Path(__file__).parent / "data" / "probability_kg.json"

    # Only these agent→claim_type combinations are meaningful for ISRID grounding.
    # Weather and logistics agents don't produce subject terrain/status claims.
    ALLOWED_CLAIMS: Dict[str, set] = {
        "path":      {ClaimType.TERRAIN, ClaimType.COMBINED},
        "interview": {ClaimType.TERRAIN, ClaimType.STATUS, ClaimType.COMBINED},
        "history":   {ClaimType.TERRAIN, ClaimType.STATUS, ClaimType.COMBINED},
        "photo":     {ClaimType.STATUS},
        "health":    {ClaimType.STATUS},
        "weather":   set(),   # weather forecasts ≠ subject terrain claims
        "logistics": set(),
    }

    @classmethod
    def _agent_key(cls, agent_name: str) -> str:
        """Normalise agent name to ALLOWED_CLAIMS key (first segment before '.')."""
        return agent_name.split(".")[0].split("-")[0].lower()

    # Keyword tables for heuristic fallback
    _SUBJECT_KEYWORDS = [
        "hiker", "climber", "dementia", "child", "hunter", "camper",
        "skier", "swimmer", "boater", "trail runner", "elderly",
        "alzheimer", "autistic", "despondent",
    ]
    _TERRAIN_KEYWORDS: Dict[str, List[str]] = {
        "mountainous": ["mountain", "alpine", "peak", "ridge", "summit", "rocky", "cliff", "steep"],
        "flat":        ["flat", "plain", "field", "meadow", "valley", "open", "prairie"],
        "water":       ["river", "lake", "ocean", "stream", "creek", "flood", "pond", "coast"],
        "cave":        ["cave", "cavern", "underground", "tunnel"],
    }
    _STATUS_KEYWORDS: Dict[str, List[str]] = {
        "well":     ["found", "alive", "safe", "rescued", "survived", "unharmed", "healthy"],
        "injured":  ["injured", "hurt", "wounded", "medical", "trauma", "broken", "hypothermia"],
        "deceased": ["dead", "deceased", "fatality", "body found", "doa", "died"],
    }

    def __init__(self, gemini_model=None):
        self.gemini_model = gemini_model
        self.kg:       Optional[ProbabilityKG] = None
        self.grounder: Optional[KGGrounding]  = None
        self.detector = ContradictionDetector(LOW_PROBABILITY_THRESHOLD, CONFIDENCE_MISMATCH_THRESHOLD)
        self.decision_maker = DecisionMaker(ACCEPT_THRESHOLD, FLAG_THRESHOLD,
                                             CANDIDATE_THRESHOLD, REJECT_SEVERITY)
        self._load_kg()

    def _load_kg(self) -> None:
        try:
            self.kg      = ProbabilityKG.load(self.KG_PATH)
            self.grounder = KGGrounding(self.kg)
        except Exception as e:
            logger.warning(f"Could not load ProbabilityKG from {self.KG_PATH}: {e}. "
                           "Verification will be skipped.")
            self.kg      = None
            self.grounder = None

    @property
    def available(self) -> bool:
        return self.kg is not None and self.grounder is not None

    # ------------------------------------------------------------------
    # Claim extraction
    # ------------------------------------------------------------------

    def extract_claims_from_text(self, agent_name: str, agent_text: str,
                                  session_id: str) -> List[AgentClaim]:
        """Extract AgentClaims from free-form agent output text."""
        if self.gemini_model:
            claims = self._extract_with_gemini(agent_name, agent_text, session_id)
            if claims:
                return claims
        return self._heuristic_claim_extraction(agent_name, agent_text, session_id)

    def _extract_with_gemini(self, agent_name: str, agent_text: str,
                              session_id: str) -> List[AgentClaim]:
        prompt = CLAIM_EXTRACTION_PROMPT.format(
            agent_name=agent_name,
            agent_text=agent_text[:2000],
        )
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 500},
            )
            raw = response.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            extracted = json.loads(raw)
            claims: List[AgentClaim] = []
            for i, item in enumerate(extracted.get("claims", [])):
                try:
                    claims.append(AgentClaim(
                        claim_id       = f"{session_id}:{agent_name}:claim_{i}",
                        source_agent   = agent_name,
                        claim_type     = ClaimType(item.get("claim_type", "terrain")),
                        scenario_id    = session_id,
                        subject_type   = item.get("subject_type", "unknown"),
                        scenario_type  = item.get("scenario_type"),
                        predicted_value= item.get("predicted_value", ""),
                        confidence     = float(item.get("confidence", 0.5)),
                        reasoning      = item.get("reasoning", ""),
                        raw_response   = agent_text[:300],
                    ))
                except Exception as e:
                    logger.debug(f"Skipping malformed claim item from {agent_name}: {e}")
            return claims
        except Exception as e:
            logger.warning(f"Gemini claim extraction failed for {agent_name}: {e}")
            return []

    def _heuristic_claim_extraction(self, agent_name: str, agent_text: str,
                                     session_id: str) -> List[AgentClaim]:
        """Keyword-based fallback: extract up to 1 terrain claim from text."""
        text_lower = agent_text.lower()
        subject = next((s for s in self._SUBJECT_KEYWORDS if s in text_lower), "unknown")

        for terrain, keywords in self._TERRAIN_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return [AgentClaim(
                    claim_id       = f"{session_id}:{agent_name}:terrain_heuristic",
                    source_agent   = agent_name,
                    claim_type     = ClaimType.TERRAIN,
                    scenario_id    = session_id,
                    subject_type   = subject,
                    scenario_type  = None,
                    predicted_value= terrain,
                    confidence     = 0.5,
                    reasoning      = "Heuristic extraction from text keywords",
                    raw_response   = agent_text[:200],
                )]
        return []

    # ------------------------------------------------------------------
    # Main verification entry point
    # ------------------------------------------------------------------

    def verify_session(self, session_id: str,
                       agent_outputs: Dict[str, str]) -> Dict[str, Any]:
        """
        Run full MAKE2026 verification pipeline on all agent outputs for a session.

        Args:
            session_id:    The SAR session identifier.
            agent_outputs: Mapping of agent_name → raw output text.

        Returns:
            Structured report dict (see plan for schema).
        """
        if not self.available:
            return {
                "session_id": session_id,
                "status":     "unavailable",
                "reason":     "ProbabilityKG not loaded",
                "claims":     [],
                "decisions":  [],
                "summary":    {},
            }

        all_claims: List[AgentClaim] = []
        for agent_name, text in agent_outputs.items():
            if not text:
                continue
            allowed = self.ALLOWED_CLAIMS.get(self._agent_key(agent_name))
            if allowed is not None and len(allowed) == 0:
                logger.debug(f"Skipping claim extraction for agent '{agent_name}' (not in ALLOWED_CLAIMS)")
                continue
            claims = self.extract_claims_from_text(agent_name, text, session_id)
            # Post-filter: drop claims whose type is not allowed for this agent
            if allowed is not None:
                claims = [c for c in claims if c.claim_type in allowed]
            all_claims.extend(claims)

        if not all_claims:
            return {
                "session_id": session_id,
                "status":     "no_claims",
                "claims":     [],
                "decisions":  [],
                "summary":    {"total_claims": 0, "agents_analyzed": list(agent_outputs.keys())},
            }

        groundings     = self.grounder.ground_claims(all_claims)
        contradictions = self.detector.detect_all(all_claims, groundings)
        decisions      = self.decision_maker.decide_all(groundings, contradictions)

        claim_reports = []
        for claim, grounding, contradiction, decision in zip(
                all_claims, groundings, contradictions, decisions):
            claim_reports.append({
                "claim_id":         claim.claim_id,
                "agent":            claim.source_agent,
                "claim_type":       claim.claim_type.value,
                "subject_type":     claim.subject_type,
                "predicted_value":  claim.predicted_value,
                "stated_confidence": claim.confidence,
                "reasoning":        claim.reasoning,
                "grounding": {
                    "is_grounded":    grounding.is_grounded,
                    "kg_probability": grounding.kg_probability,
                    "hop_type":       grounding.hop_type.value,
                    "sample_count":   grounding.sample_count,
                    "kg_distribution": grounding.kg_distribution,
                },
                "contradiction": {
                    "has_contradiction": contradiction.has_contradiction,
                    "type":              contradiction.contradiction_type.value,
                    "severity":          contradiction.severity,
                    "explanation":       contradiction.explanation,
                },
                "decision": {
                    "tier":             decision.tier.value,
                    "final_confidence": decision.final_confidence,
                    "recommendation":   decision.recommendation,
                    "evidence_summary": decision.evidence_summary,
                },
            })

        tier_counts: Dict[str, int] = {}
        for d in decisions:
            tier_counts[d.tier.value] = tier_counts.get(d.tier.value, 0) + 1

        grounding_rate    = sum(1 for g in groundings if g.is_grounded) / len(groundings)
        contradiction_rate = sum(1 for c in contradictions if c.has_contradiction) / len(contradictions)

        return {
            "session_id":  session_id,
            "status":      "complete",
            "claims":      claim_reports,
            "decisions":   [d.to_dict() for d in decisions],
            "summary": {
                "total_claims":       len(all_claims),
                "tier_distribution":  tier_counts,
                "agents_analyzed":    list(agent_outputs.keys()),
                "grounding_rate":     grounding_rate,
                "contradiction_rate": contradiction_rate,
            },
            "verified_at": datetime.utcnow().isoformat() + "Z",
        }
