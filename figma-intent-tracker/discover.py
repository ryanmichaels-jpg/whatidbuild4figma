"""DISCOVER stage: find LinkedIn engagement-bait / hand-raiser posts.

The target is lead-magnet posts where the author asks people to comment to get
something ("comment 'guide' and I'll DM you the Figma-alternative playbook",
"comment below and I'll show you how to do what Figma does"). On those posts the
value IS the commenters: each comment is a person raising their hand.

Apify-only and cookie-free, via a native LinkedIn post-search actor
(harvestapi~linkedin-post-search) that returns each post's full body text and its
engagement counts. That lets us detect the bait call-to-action in the actual post
body and rank candidates by comment volume -- the reliable proxy for "this post is
harvesting commenters". Demo mode reads committed synthetic posts.
"""
from __future__ import annotations

import json
import re
import os
from typing import Optional

from apify_run import run_actor

# Discovery queries come from the Config-2026 displacement map: for each Figma
# surface, hunt engagement-bait posts about the COMPETITOR tool/workflow Figma now
# displaces (After Effects -> Figma Motion, Webflow -> Sites, design-to-code ->
# Code Layers, etc.). The commenters on those posts are in-market for what Figma does.
_DISP = os.path.join(os.path.dirname(__file__), "data", "displacement_map.json")

_FALLBACK_QUERIES = [
    "comment and I'll send you the guide design UI",
    "After Effects alternative UI animation comment",
    "design to code workflow comment guide",
    "build a website no code comment guide",
    "pitch deck design comment guide",
]


def _load_displacement() -> dict:
    try:
        with open(_DISP, "r", encoding="utf-8") as fh:
            return json.load(fh)["surfaces"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return {}


def _displacement_queries() -> list[str]:
    qs = [q for s in _load_displacement().values() for q in s.get("queries", [])]
    return qs or _FALLBACK_QUERIES


# name -> surface, for every displaced tool in the map (lowercased) -- used to confirm
# a discovered post is actually ABOUT a tool Figma displaces (precision over loose search).
def _displaced_tools() -> dict:
    out = {}
    for surface, s in _load_displacement().items():
        for tool in s.get("tool_keywords", []):
            out[tool.lower()] = surface
    return out


DISCOVERY_QUERIES = _displacement_queries()
DISPLACED_TOOLS = _displaced_tools()


def matched_displaced_tools(text: str) -> list[str]:
    """Which Figma-displaced tools the post body names (e.g. 'after effects', 'webflow').

    Whole-word match so 'anima' (the handoff tool) does not fire on 'animation', and
    'rive' does not fire on 'arrive'.
    """
    low = (text or "").lower()
    return sorted({t for t in DISPLACED_TOOLS if re.search(rf"\b{re.escape(t)}\b", low)})

# Cues that the post BODY is engagement bait (author harvesting commenters).
BAIT_CUES = [
    "comment below",
    "comment 'guide'",
    'comment "guide"',
    "comment the word",
    "comment and i",
    "i'll send",
    "i will send",
    "i'll show you",
    "i'll dm",
    "dm you",
    "send you the",
    "i'll share",
    "drop a comment",
    "tag someone",
    "tag a",
    "raise your hand",
    "want the link",
    "want it",
    "link in the comments",
    "save this",
    "\U0001f447",  # down-pointing finger emoji
]

_DEMO_POSTS = os.path.join(os.path.dirname(__file__), "data", "demo_posts.json")
APIFY_POST_SEARCH_ACTOR = os.environ.get("APIFY_POST_SEARCH_ACTOR", "harvestapi~linkedin-post-search")
MAX_POSTS_PER_QUERY = int(os.environ.get("APIFY_MAX_POSTS", "8"))


def discover_demo() -> list[dict]:
    with open(_DEMO_POSTS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def bait_score(text: str) -> int:
    """How many engagement-bait cues appear in a post body."""
    low = (text or "").lower()
    return sum(cue in low for cue in BAIT_CUES)


def _comment_count(item: dict) -> int:
    eng = item.get("engagement") or {}
    return int(eng.get("comments") or 0)


def discover_live(
    queries: Optional[list[str]] = None,
    max_posts: Optional[int] = None,
    posted_limit: str = "any",
) -> list[dict]:
    """Return Figma posts ranked by (bait cues in body, then comment volume).

    Each post: url, title, content, comment_count, reaction_count, bait_score.
    """
    queries = queries or DISCOVERY_QUERIES
    body = {
        "searchQueries": queries,
        "maxPosts": max_posts or MAX_POSTS_PER_QUERY,
        "sortBy": "relevance",
        "postedLimit": posted_limit,
        "scrapeComments": False,  # cheap discovery pass; comments are pulled later for the top posts
    }
    items = run_actor(APIFY_POST_SEARCH_ACTOR, body)

    by_url: dict[str, dict] = {}
    for it in items:
        url = (it.get("linkedinUrl") or it.get("shareLinkedinUrl") or "").split("?")[0]
        if not url or "/posts/" not in url:
            continue
        if url in by_url:
            continue
        content = it.get("content") or ""
        reactions = it.get("engagement", {}).get("reactions")
        reaction_count = sum(r.get("count", 0) for r in reactions) if isinstance(reactions, list) else 0
        matched = matched_displaced_tools(content)
        by_url[url] = {
            "url": url,
            "title": content.split("\n", 1)[0][:140] or "(no text)",
            "content": content,
            "comment_count": _comment_count(it),
            "reaction_count": reaction_count,
            "bait_score": bait_score(content),
            "matched_tools": matched,  # Figma-displaced tools named in the post
            "surfaces": sorted({DISPLACED_TOOLS[t] for t in matched}),
        }

    posts = list(by_url.values())
    # precision: posts that actually name a Figma-displaced tool first, then bait, then volume
    posts.sort(key=lambda p: (bool(p["matched_tools"]), p["bait_score"], p["comment_count"]), reverse=True)
    return posts


def discover(mode: str, **kwargs) -> list[dict]:
    return discover_live(**kwargs) if mode == "live" else discover_demo()
