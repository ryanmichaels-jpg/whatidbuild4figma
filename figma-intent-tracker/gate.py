"""The trust gate.

No lead is surfaced without a verbatim evidence quote drawn from the real
comment. This is a deterministic check the LLM cannot talk its way past: if the
quote is not an exact substring of the comment, the lead is dropped even when the
model was confident. Same rule across every Figma artifact in this portfolio.
"""
from __future__ import annotations

from schema import Classification, Commenter, Decision, IntentType, TitleResult

CONFIDENCE_THRESHOLD = 0.6
SURFACE_INTENTS = {IntentType.active_need, IntentType.evaluating}


def is_verbatim(quote: str, comment: str) -> bool:
    """True only if `quote` is a non-empty exact substring of `comment`."""
    q = (quote or "").strip()
    return bool(q) and q in comment


def decide(commenter: Commenter, title: TitleResult, cls: Classification) -> tuple[Decision, str]:
    """Apply the gate to a classified, ICP-matched commenter.

    Order matters: the verbatim check is first so a hallucinated quote can never
    be rescued by a high confidence score.
    """
    if not is_verbatim(cls.evidence_quote, commenter.comment_text):
        return Decision.drop, "evidence quote not verbatim -- failed trust gate"

    if cls.intent_type == IntentType.noise:
        return Decision.drop, "intent classified as noise"

    persona = title.persona.value if title.persona else "unknown"
    if cls.intent_type in SURFACE_INTENTS and cls.confidence >= CONFIDENCE_THRESHOLD:
        return (
            Decision.surface,
            f"{persona} with {cls.intent_type.value} intent at confidence {cls.confidence:.2f}",
        )

    return (
        Decision.review,
        f"ambiguous: {cls.intent_type.value} intent at confidence {cls.confidence:.2f}",
    )
