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
from collections import Counter
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
        author = it.get("author") or {}
        reactions = it.get("engagement", {}).get("reactions")
        reaction_count = sum(r.get("count", 0) for r in reactions) if isinstance(reactions, list) else 0
        matched = matched_displaced_tools(content)
        by_url[url] = {
            "url": url,
            "title": content.split("\n", 1)[0][:140] or "(no text)",
            "content": content,
            "author": author.get("name", ""),
            "author_headline": author.get("headline", ""),
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


# --- Smart layer: emulate the boolean query the actor can't run ------------------
# The actor is fuzzy keyword-only (no AND/OR/NOT/quotes). We get recall from many
# simple queries (OR), then enforce precision in code: require a displaced-tool
# mention (AND), require a bait cue if asked (AND), and drop off-domain noise (NOT).

# NOT clause: clear non-Figma domains that keep polluting results.
STOP_LIST = [
    "outbound", "cold email", "cold outreach", "appointment setting", "lead generation",
    "real estate", "realtor", "crypto", "blockchain", "web3", "nft", "forex", "dropship",
    "network marketing", "affiliate marketing", "we're hiring", "open to work",
]
_FOLLOWER_HEADLINE = re.compile(r"^\s*[\d,]+\s+followers\s*$", re.I)


def excluded_reason(content: str, author_headline: str = "") -> str | None:
    """NOT clause: why a post is off-domain noise, or None to keep it."""
    blob = f"{content} {author_headline}".lower()
    for term in STOP_LIST:
        if re.search(rf"\b{re.escape(term)}\b", blob):
            return term
    if _FOLLOWER_HEADLINE.match(author_headline or ""):
        return "follower-count account"
    return None


def filter_candidates(posts: list[dict], require_tool: bool = True, require_bait: bool = False):
    """Apply AND/NOT precision to the recalled candidates. Returns (kept, drop_reasons)."""
    kept, drops = [], Counter()
    for p in posts:
        ex = excluded_reason(p.get("content", ""), p.get("author_headline", ""))
        if ex:
            drops[f"stop:{ex}"] += 1
            continue
        if require_tool and not p.get("matched_tools"):
            drops["no_displaced_tool"] += 1
            continue
        if require_bait and not p.get("bait_score"):
            drops["no_bait_cue"] += 1
            continue
        kept.append(p)
    kept.sort(
        key=lambda p: (len(p.get("matched_tools", [])), p.get("bait_score", 0), p.get("comment_count", 0)),
        reverse=True,
    )
    return kept, drops


def smart_discover(
    queries: Optional[list[str]] = None,
    max_posts: Optional[int] = None,
    posted_limit: str = "6months",
    require_tool: bool = True,
    require_bait: bool = False,
) -> list[dict]:
    """Recall via the dumb actor, precision via client-side boolean filtering."""
    posts = discover_live(queries=queries, max_posts=max_posts, posted_limit=posted_limit)
    kept, drops = filter_candidates(posts, require_tool=require_tool, require_bait=require_bait)
    kept_n, total = len(kept), len(posts)
    print(f"[smart_discover] {total} recalled -> {kept_n} kept; dropped {dict(drops)}")
    return kept


def discover(mode: str, **kwargs) -> list[dict]:
    return smart_discover(**kwargs) if mode == "live" else discover_demo()
