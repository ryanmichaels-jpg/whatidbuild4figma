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
from functools import lru_cache

from schema import Classification, Commenter, classification_json_schema

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


def classify(commenter: Commenter, mode: str, post_type: str | None = None) -> Classification:
    return classify_live(commenter, post_type) if mode == "live" else classify_demo(commenter)
