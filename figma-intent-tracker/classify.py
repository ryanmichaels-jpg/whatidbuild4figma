"""Intent classifier -- the one bounded LLM step.

Demo mode replays recorded claude-haiku-4-5 outputs (zero credentials). Live mode
calls Anthropic with structured output so the response is schema-constrained: the
model must return every field, and a downstream gate (gate.py) still rejects any
non-verbatim evidence quote. Lightest-safe-solution: the cheap haiku model runs
only on the narrow set of commenters that already passed the free ICP filter.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from functools import lru_cache

from schema import Classification, Commenter, IntentType, classification_json_schema

# Self-consistency config. Borderline = a surface-eligible call that is easy to flip
# (low-ish confidence or a one/two-word quote like "Website"). We re-sample those and
# vote, so a comment that the model labels inconsistently lands consistently.
SELF_CONSISTENCY_SAMPLES = int(os.environ.get("SELF_CONSISTENCY_SAMPLES", "3"))
_SURFACE_INTENTS = {IntentType.active_need, IntentType.evaluating}
# tie-break order: most conservative first
_INTENT_PRIORITY = [IntentType.noise, IntentType.curious, IntentType.evaluating, IntentType.active_need]

CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "claude-haiku-4-5")
_RECORDED = os.path.join(os.path.dirname(__file__), "data", "recorded_classifications.json")

SYSTEM_PROMPT = (
    "You classify LinkedIn comments to find people in the market for a design or "
    "UI-prototyping tool. The comments are on posts about designing and building "
    "interfaces (often with AI tools like Claude). A strong lead is someone "
    "actively trying to design, build a UI, or set up a design workflow -- they "
    "are a potential design-tool buyer or user. "
    "Return only the requested JSON. The evidence_quote MUST be copied verbatim "
    "from the comment -- an exact substring, no paraphrasing, no invention. "
    "If the comment is praise, off-topic, or not about doing design work, use "
    "intent_type 'noise'. Ground need and suggested_angle only in what the comment "
    "actually says; suggested_angle is a one-line angle for how Figma (design, "
    "prototyping, Dev Mode, AI/Make) fits the stated need."
)


@lru_cache(maxsize=1)
def _recorded() -> dict:
    with open(_RECORDED, "r", encoding="utf-8") as fh:
        return json.load(fh)


def classify_demo(commenter: Commenter) -> Classification:
    """Replay a recorded classification for a demo commenter."""
    rec = _recorded().get(commenter.profile_url)
    if rec is None:
        raise KeyError(f"no recorded classification for {commenter.profile_url}")
    return Classification(**rec)


# How the post type changes the reading of a comment (the "post is the prior" rule).
_POST_CONTEXT = {
    "lead_magnet": (
        "This is a lead-magnet post (the author offers a guide/tool for commenting), "
        "so a short comment asking for the asset ('guide', 'interested', 'send it') IS "
        "an active hand-raise -- treat it as active_need, not noise."
    ),
    "tool_question": "This post asks what tools people use, so naming a tool or a need is evaluating/active_need.",
    "tool_comparison": "This post compares tools, so stating a preference or gap is evaluating.",
}


def classify_live(commenter: Commenter, post_type: str | None = None) -> Classification:
    """Call claude-haiku-4-5 with a schema-constrained response, conditioned on post type."""
    from anthropic import Anthropic  # imported lazily so demo mode needs no SDK

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    context = _POST_CONTEXT.get(post_type or "", "")
    user = (
        f"Post type: {post_type or 'unknown'}. {context}\n"
        f"Comment: {commenter.comment_text!r}\n"
        f"Author headline: {commenter.headline or 'unknown'}\n"
        "Classify this commenter's design-tool intent."
    )
    resp = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": classification_json_schema(),
            }
        },
    )
    payload = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    return Classification(**json.loads(payload))


def _is_borderline(cls: Classification) -> bool:
    """A surface-eligible call that is easy to flip -> worth re-sampling."""
    return cls.intent_type in _SURFACE_INTENTS and (
        cls.confidence < 0.8 or len(cls.evidence_quote.split()) <= 2
    )


def resolve_votes(votes: list[Classification]) -> Classification:
    """Majority-vote intent across re-samples; conservative tie-break; scale confidence
    by agreement so a split vote (e.g. 2 active_need / 1 noise) drops below the surface
    threshold and routes to review instead of flip-flopping."""
    counts = Counter(v.intent_type for v in votes)
    top = max(counts.values())
    winners = [i for i, c in counts.items() if c == top]
    winner = min(winners, key=lambda i: _INTENT_PRIORITY.index(i))
    agreement = counts[winner] / len(votes)
    rep = next(v for v in votes if v.intent_type == winner)
    return Classification(
        intent_type=winner,
        need=rep.need,
        evidence_quote=rep.evidence_quote,
        confidence=round(rep.confidence * agreement, 2),
        suggested_angle=rep.suggested_angle,
    )


def classify(commenter: Commenter, mode: str, post_type: str | None = None) -> Classification:
    if mode != "live":
        return classify_demo(commenter)
    first = classify_live(commenter, post_type)
    if not _is_borderline(first):
        return first
    votes = [first] + [
        classify_live(commenter, post_type) for _ in range(max(0, SELF_CONSISTENCY_SAMPLES - 1))
    ]
    return resolve_votes(votes)
