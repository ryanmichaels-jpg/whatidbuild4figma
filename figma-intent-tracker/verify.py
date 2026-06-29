"""VERIFY stage: a deterministic quality check on surfaced leads.

The gate guarantees the evidence quote is a real substring of the comment, but not
that the quote actually expresses tooling intent. The most common LLM mislabel is
scoring praise ("love this!") as active_need with a real verbatim quote -- which the
gate cannot catch. This pass downgrades a surfaced lead to review when its evidence
quote reads as praise/celebration and carries no tooling-intent signal.

Deterministic and zero-cost so it runs in demo and live alike. A heavier LLM
"does this quote justify the label?" verifier could layer on top in live mode.
"""
from __future__ import annotations

from schema import Decision, Lead

_PRAISE = [
    "love this", "love it", "great post", "great thread", "amazing", "congrats",
    "congratulations", "awesome", "well done", "nice work", "so cool", "this is cool",
    "this is great", "following", "saving this", "thanks for sharing", "good stuff",
    "so true", "brilliant", "beautiful", "insightful", "wow", "🔥", "👏", "🙌", "💯", "🎉",
]

# If any of these appear, the quote carries real tooling/intent signal -> not praise.
_INTENT_SIGNALS = [
    "switch", "alternativ", "instead", "trying", "evaluat", "comparing", "compare",
    "building", "build", "migrat", "need", "looking for", "guide", "send me", "dm me",
    "using", "use ", "tool", "figma", "claude", "framer", "webflow", "sketch", "cursor",
    "prototyp", "design system", "handoff", "seats", "pricing",
]


def looks_like_praise(quote: str) -> bool:
    """True if the quote is praise/celebration with no tooling-intent signal."""
    low = (quote or "").lower().strip()
    if not any(p in low for p in _PRAISE):
        return False
    return not any(s in low for s in _INTENT_SIGNALS)


def verify(lead: Lead) -> tuple[Decision, str | None]:
    """Re-check a surfaced lead. Returns (possibly downgraded decision, quality_flag)."""
    if lead.decision != Decision.surface or lead.classification is None:
        return lead.decision, None
    if looks_like_praise(lead.classification.evidence_quote):
        return Decision.review, "verification: evidence quote reads as praise, not tooling intent"
    return lead.decision, None
