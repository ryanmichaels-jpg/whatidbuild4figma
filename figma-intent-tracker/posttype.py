"""POST-TYPE stage: decide if a post is worth mining, BEFORE touching its comments.

This runs first. The same comment means different things depending on the post, so
we classify the post and only mine the types where commenters reveal their tooling:
lead_magnet ("comment 'guide' and I'll send it"), tool_question ("what are you using
instead of X?"), and tool_comparison ("Figma Motion vs After Effects?"). Showcases/
tutorials (mostly praise) and off_topic posts (not about design/build tooling) are
dropped here -- so we never spend comment-scraping or LLM budget on them.

A deterministic lead-magnet detector catches the highest-value structure for free;
otherwise a cheap schema-constrained LLM call types the post. Demo mode replays
recorded post classifications (zero credentials).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from schema import QUALIFYING_POST_TYPES, PostClassification, PostType

POST_CLASSIFIER_MODEL = os.environ.get("POST_CLASSIFIER_MODEL", "claude-haiku-4-5")
_RECORDED = os.path.join(os.path.dirname(__file__), "data", "demo_post_classifications.json")

# Deterministic "comment to get the asset" structure -- the clearest lead_magnet signal.
_LEAD_MAGNET_CUES = [
    r"comment\b.{0,30}\bi'?ll (send|dm|share)",
    r"\btype\b\s+[\"'a-z]+\s+(below|in the comments)",
    r"comment\s+[\"'][a-z ]+[\"']",
    r"drop\s+a\s+comment.{0,30}(send|dm|guide)",
    r"dm\s+you\s+the\b",
    r"\bcomment\b.{0,20}\bbelow\b.{0,40}\b(guide|link|template|playbook|pdf)",
]

SYSTEM_PROMPT = (
    "You decide whether a LinkedIn post is a useful lead source for a design/build "
    "TOOLING vendor (e.g. Figma -- design, FigJam, Dev Mode, Make). A post QUALIFIES "
    "only if it is specifically about design/build tooling: it (a) names specific "
    "design/build tools (Figma, FigJam, Sketch, Adobe XD, Photoshop, Illustrator, "
    "Framer, Webflow, Canva, Penpot, Claude, Cursor, v0, Bolt, Lovable, etc.) AND "
    "offers a tool/workflow guide to comment for, OR (b) asks what tools others use / "
    "compares tools / solicits tool recommendations or alternatives. It does NOT "
    "qualify on the generic word 'design' (design thinking, design your career, org "
    "design), nor on unrelated topics (finance, HR, real estate), nor on a tutorial "
    "that merely USES a tool without asking about tool choice. Classify the post type. "
    "Return only JSON."
)

_POST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["post_type", "tools_mentioned", "reason"],
    "properties": {
        "post_type": {
            "type": "string",
            "enum": [e.value for e in PostType],
            "description": (
                "lead_magnet: offers an asset to comment for; tool_question: asks what "
                "tools others use; tool_comparison: compares/weighs named tools; showcase: "
                "shows a build/tutorial (no tool-choice ask); off_topic: not about tooling."
            ),
        },
        "tools_mentioned": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string", "description": "one short sentence"},
    },
}


def _finalize(post_type: PostType, tools: list[str], reason: str, source: str) -> PostClassification:
    return PostClassification(
        post_type=post_type,
        qualifies=post_type in QUALIFYING_POST_TYPES,
        tools_mentioned=tools,
        reason=reason,
        source=source,
    )


def detect_lead_magnet(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(p, low) for p in _LEAD_MAGNET_CUES)


@lru_cache(maxsize=1)
def _recorded() -> dict:
    with open(_RECORDED, "r", encoding="utf-8") as fh:
        return json.load(fh)


def classify_post_demo(post: dict) -> PostClassification:
    rec = _recorded().get(post["url"])
    if rec is None:
        raise KeyError(f"no recorded post classification for {post['url']}")
    return _finalize(PostType(rec["post_type"]), rec.get("tools_mentioned", []), rec["reason"], "demo")


def classify_post_live(post: dict) -> PostClassification:
    content = post.get("content") or post.get("title") or ""
    if detect_lead_magnet(content):
        return _finalize(PostType.lead_magnet, [], "deterministic: comment-for-asset structure", "live")

    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=POST_CLASSIFIER_MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content[:1200]}],
        output_config={"format": {"type": "json_schema", "schema": _POST_SCHEMA}},
    )
    payload = json.loads("".join(b.text for b in resp.content if getattr(b, "type", None) == "text"))
    return _finalize(PostType(payload["post_type"]), payload.get("tools_mentioned", []), payload["reason"], "live")


def classify_post(post: dict, mode: str) -> PostClassification:
    return classify_post_live(post) if mode == "live" else classify_post_demo(post)
