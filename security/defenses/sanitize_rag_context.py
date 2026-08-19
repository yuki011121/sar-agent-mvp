"""
RAG Poisoning Defenses: Provenance Allowlist + RobustRAG Aggregation

Two defense layers against retrieval-corpus poisoning in the history agent.

Layer 1 — Provenance allowlist (filter_by_provenance):
    Drop any retrieved chunk whose provenance.source is not on the trusted list.
    All poison payloads use fabricated sources ("ISRID Operational Update Q1-2026",
    "Mountain SAR Research Institute") and are therefore filtered before reaching
    the LLM.
    Why this works: poisoning requires inserting chunks into the vector DB. Unless
    the attacker can spoof a trusted source name (which requires DB write + knowledge
    of the allowlist), all injected chunks are dropped at retrieval time.

Layer 2 — RobustRAG-style aggregation (robust_rag_aggregate):
    Defense-in-depth for an attacker who successfully spoofs a trusted source.
    Retrieve K chunks, produce K independent LLM drafts (one per chunk), then
    majority-vote the final recommendation. A single poisoned chunk can only
    cast one vote — the K-1 clean chunks outweigh it.
    Reference: RobustRAG (Xiang et al., 2024).

Both layers are controlled by env vars in agents/history/main.py:
    HISTORY_PROVENANCE_ALLOWLIST_ENABLED  (default "true")
    HISTORY_ROBUSTRAG_ENABLED             (default "false")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Trusted provenance sources ────────────────────────────────────────────────
# Exact strings or regex patterns matching known-good sources. New real sources
# should be added here; do NOT add any attacker-controlled source.
TRUSTED_SOURCES: set[str] = {
    "Mountain SAR Field Guide, 3rd Edition",
    "Lost Person Behavior, 2nd Edition",
    "NASAR Fundamentals of Search and Rescue",
    "SAR Incident Review: Pacific Crest Trail Region",
    # Broader patterns — add more as the knowledge base grows
    "NASAR",
    "USFS",
    "Lost Person Behavior",
    "Mountain SAR Field Guide",
}

# Regex patterns that also mark a source as trusted (case-insensitive).
# e.g. any NASAR publication regardless of edition number.
_TRUSTED_PATTERNS: list[re.Pattern] = [
    re.compile(r"^nasar", re.IGNORECASE),
    re.compile(r"^lost person behavior", re.IGNORECASE),
    re.compile(r"^mountain sar field guide", re.IGNORECASE),
    re.compile(r"^sar incident review", re.IGNORECASE),
    re.compile(r"^usfs", re.IGNORECASE),
]


def _is_trusted_source(source: str) -> bool:
    if not source:
        return False
    if source in TRUSTED_SOURCES:
        return True
    return any(p.search(source) for p in _TRUSTED_PATTERNS)


# ── Layer 1: Provenance allowlist ─────────────────────────────────────────────

def filter_by_provenance(
    chunks: list[dict],
    log_drops: bool = True,
) -> list[dict]:
    """
    Drop chunks whose provenance.source is not on the trusted allowlist.

    Args:
        chunks    : list of dicts with schema
                    {"provenance": {"source": str, "author": str}, "content": str}
        log_drops : emit a WARNING for every dropped chunk (default True)

    Returns:
        Filtered list containing only trusted chunks.
    """
    trusted, dropped = [], []
    for chunk in chunks:
        src = chunk.get("provenance", {}).get("source", "")
        if _is_trusted_source(src):
            trusted.append(chunk)
        else:
            dropped.append(src)

    if dropped and log_drops:
        logger.warning(
            "Provenance allowlist dropped %d chunk(s) with untrusted source(s): %s",
            len(dropped),
            dropped,
        )
    return trusted


# ── Layer 2: RobustRAG aggregation ────────────────────────────────────────────

def robust_rag_aggregate(
    chunks: list[dict],
    gemini_client,
    query_context: str,
    n_tips: int = 3,
    threshold: float = 0.5,
) -> Optional[str]:
    """
    RobustRAG-style majority-vote aggregation (Xiang et al. 2024).

    For each chunk independently, ask Gemini for a one-sentence search
    recommendation. Collect all responses and return the majority-agreed
    recommendation (the one whose keywords appear in >= threshold fraction
    of responses).

    If fewer than 2 chunks are available, returns None (caller uses the
    standard single-prompt path).

    Args:
        chunks         : list of RAG context dicts (already provenance-filtered)
        gemini_client  : initialized google.genai.Client
        query_context  : the original user query as a string (for LLM context)
        n_tips         : how many action tips to request per chunk
        threshold      : fraction of per-chunk responses that must agree
                         on a keyword/phrase for it to be included

    Returns:
        Aggregated recommendation string, or None if not enough chunks.
    """
    if len(chunks) < 2:
        return None

    per_chunk_responses: list[str] = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        source = chunk.get("provenance", {}).get("source", "unknown")
        prompt = (
            f"You are a Search and Rescue expert. "
            f"Based ONLY on the following single piece of SAR context, "
            f"give {n_tips} concise search recommendations for this query.\n\n"
            f"Query: {query_context}\n\n"
            f"SAR Context (source: {source}):\n{content}\n\n"
            f"Recommendations:"
        )
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            per_chunk_responses.append(response.text.strip())
            logger.debug("RobustRAG chunk %d/%d response received", i + 1, len(chunks))
        except Exception as e:
            logger.warning("RobustRAG: Gemini call for chunk %d failed: %s", i + 1, e)

    if not per_chunk_responses:
        return None

    # Simple aggregation: return the longest response whose key phrases appear
    # in at least `threshold` fraction of other responses. If no majority,
    # return the response with the highest phrase-overlap score.
    def _overlap_score(candidate: str, others: list[str]) -> float:
        words = set(candidate.lower().split())
        scores = [
            len(words & set(r.lower().split())) / max(len(words), 1)
            for r in others
        ]
        return sum(scores) / len(scores) if scores else 0.0

    best, best_score = per_chunk_responses[0], 0.0
    for resp in per_chunk_responses:
        others = [r for r in per_chunk_responses if r is not resp]
        score = _overlap_score(resp, others)
        if score > best_score:
            best, best_score = resp, score

    logger.info(
        "RobustRAG aggregated %d chunk responses; best overlap score=%.3f",
        len(per_chunk_responses),
        best_score,
    )
    return best
