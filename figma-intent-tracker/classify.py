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


def classify_live(commenter: Commenter) -> Classification:
    """Call claude-haiku-4-5 with a schema-constrained response."""
    from anthropic import Anthropic  # imported lazily so demo mode needs no SDK

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    user = (
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


def classify(commenter: Commenter, mode: str) -> Classification:
    return classify_live(commenter) if mode == "live" else classify_demo(commenter)
