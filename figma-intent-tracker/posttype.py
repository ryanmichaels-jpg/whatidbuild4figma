"""POST stage: decide if a post is worth mining, BEFORE touching its comments.

Two questions, both must be yes:
  1. STRUCTURE -- does commenting reveal tooling intent? (post_type in lead_magnet /
     tool_question / tool_comparison; showcases and off_topic do not).
  2. FIGMA OVERLAP -- could Figma DISPLACE the solution the poster is offering? We
     map the post's use case to a Figma surface (design, make, sites, slides, figjam,
     dev_mode, draw, buzz, motion) using the Config-2026 capability map. If Figma
     can't do it (interior decor, CAD, pure software engineering, business coaching),
     figma_surface = none and the post is dropped.

The logic: if a poster offers something Figma also solves, and people comment to get
help/resources in that area, those commenters are in-market for what Figma does.

A deterministic "comment-for-asset" detector hints the lead_magnet structure; the
LLM still judges Figma overlap. Demo mode replays recorded judgments (zero creds).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from schema import QUALIFYING_POST_TYPES, FigmaSurface, PostClassification, PostType

POST_CLASSIFIER_MODEL = os.environ.get("POST_CLASSIFIER_MODEL", "claude-haiku-4-5")
_RECORDED = os.path.join(os.path.dirname(__file__), "data", "demo_post_classifications.json")
_CAPS = os.path.join(os.path.dirname(__file__), "data", "figma_capabilities.json")

_LEAD_MAGNET_CUES = [
    r"comment\b.{0,30}\bi'?ll (send|dm|share)",
    r"\btype\b\s+[\"'a-z]+\s+(below|in the comments)",
    r"comment\s+[\"'][a-z ]+[\"']",
    r"drop\s+a\s+comment.{0,30}(send|dm|guide)",
    r"dm\s+you\s+the\b",
    r"\bcomment\b.{0,20}\bbelow\b.{0,40}\b(guide|link|template|playbook|pdf)",
]


@lru_cache(maxsize=1)
def _capability_summary() -> str:
    with open(_CAPS, "r", encoding="utf-8") as fh:
        caps = json.load(fh)
    lines = []
    for key, s in caps["surfaces"].items():
        lines.append(f"- {key}: {s['what']} (displaces: {', '.join(s['displaces'][:4])})")
    not_figma = "; ".join(caps["not_figma"])
    return "FIGMA SURFACES:\n" + "\n".join(lines) + f"\n\nNOT FIGMA (figma_surface=none): {not_figma}"


def _system_prompt() -> str:
    return (
        "You triage LinkedIn posts as lead sources for Figma. For each post decide:\n"
        "1) post_type: lead_magnet (offers an asset to comment for) / tool_question (asks "
        "what tools people use) / tool_comparison (compares/weighs tools) / showcase "
        "(shows a build, no tool-choice ask) / off_topic.\n"
        "2) figma_surface: which Figma surface could DISPLACE the solution the poster is "
        "offering or discussing -- i.e. could a person doing this instead do it in Figma? "
        "Use 'none' if Figma cannot solve this use case.\n"
        "Judge overlap by the USE CASE, not the word 'design'. Building a website -> sites; "
        "making a deck -> slides; building an app/UI from a prompt -> make; animating UI -> "
        "motion; diagramming/whiteboarding -> figjam; UI/product design -> design. Interior "
        "room redesign, CAD, photo retouching, code review/refactoring, and business coaching "
        "are NOT Figma (none).\n\n" + _capability_summary() + "\n\nReturn only JSON."
    )


_POST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["post_type", "figma_surface", "use_case", "tools_mentioned", "reason"],
    "properties": {
        "post_type": {
            "type": "string",
            "enum": [e.value for e in PostType],
            "description": "lead_magnet / tool_question / tool_comparison / showcase / off_topic",
        },
        "figma_surface": {
            "type": "string",
            "enum": [e.value for e in FigmaSurface],
            "description": "Which Figma surface could displace the post's use case; 'none' if Figma can't.",
        },
        "use_case": {"type": "string", "description": "What the poster is offering or addressing, in a few words."},
        "tools_mentioned": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string", "description": "one short sentence"},
    },
}


def _finalize(post_type, figma_surface, use_case, tools, reason, source) -> PostClassification:
    qualifies = post_type in QUALIFYING_POST_TYPES and figma_surface != FigmaSurface.none
    return PostClassification(
        post_type=post_type, figma_surface=figma_surface, use_case=use_case,
        qualifies=qualifies, tools_mentioned=tools, reason=reason, source=source,
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
    return _finalize(
        PostType(rec["post_type"]),
        FigmaSurface(rec.get("figma_surface", "none")),
        rec.get("use_case", ""),
        rec.get("tools_mentioned", []),
        rec["reason"],
        "demo",
    )


def classify_post_live(post: dict) -> PostClassification:
    content = post.get("content") or post.get("title") or ""
    hint = ""
    if detect_lead_magnet(content):
        hint = (
            "\n\nNote: this post has a 'comment for an asset' call-to-action. If its asset "
            "maps to a Figma surface, it is lead_magnet; if the asset is off Figma's surface "
            "(figma_surface=none), it is off_topic."
        )

    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=POST_CLASSIFIER_MODEL,
        max_tokens=350,
        system=_system_prompt(),
        messages=[{"role": "user", "content": content[:1200] + hint}],
        output_config={"format": {"type": "json_schema", "schema": _POST_SCHEMA}},
    )
    p = json.loads("".join(b.text for b in resp.content if getattr(b, "type", None) == "text"))
    return _finalize(
        PostType(p["post_type"]), FigmaSurface(p["figma_surface"]),
        p.get("use_case", ""), p.get("tools_mentioned", []), p["reason"], "live",
    )


def classify_post(post: dict, mode: str) -> PostClassification:
    return classify_post_live(post) if mode == "live" else classify_post_demo(post)
