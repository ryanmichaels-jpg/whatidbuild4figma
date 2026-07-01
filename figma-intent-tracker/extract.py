"""EXTRACT stage: pull commenters from intent posts.

Demo mode reads committed synthetic commenters. Live mode calls a cookie-free
Apify LinkedIn post-comments actor (slug from APIFY_ACTOR; default
harvestapi~linkedin-post-comments, which authenticates server-side so no LinkedIn
session cookie is required), maps its output onto the Commenter trust-contract
model, and writes the raw scrape to data/comments-live.json -- which is
gitignored, so real people's data never lands in the repo.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from apify_run import run_actor
from schema import Commenter


def _company_from_headline(headline: Optional[str]) -> Optional[str]:
    m = re.search(r"\bat\s+([A-Za-z0-9][\w&.,'\- ]{1,40})", headline or "")
    return m.group(1).strip(" .|") if m else None


def _company(actor: dict) -> Optional[str]:
    """Best-effort current employer from the profile (current role -> latest experience -> headline)."""
    cp = actor.get("currentPosition")
    if isinstance(cp, list) and cp:
        c = cp[0].get("companyName") or cp[0].get("company")
        if c:
            return c
    exp = actor.get("experience")
    if isinstance(exp, list) and exp:
        c = exp[0].get("companyName")
        if c:
            return c
    return _company_from_headline(actor.get("headline") or actor.get("position"))

_DEMO_COMMENTS = os.path.join(os.path.dirname(__file__), "data", "demo_comments.json")
_LIVE_OUT = os.path.join(os.path.dirname(__file__), "data", "comments-live.json")

APIFY_ACTOR = os.environ.get("APIFY_ACTOR", "harvestapi~linkedin-post-comments")
# On a lead-magnet post the value IS the commenters, so scrape deep: a viral bait post
# can carry 100+ hand-raisers, and a low cap silently leaves ICP leads unscraped (a 40-cap
# on one such post surfaced 3 ICP designers; scraping the full ~90 surfaced 8). Tradeoff:
# more comments = more Apify credits + more classifier calls -- but the deterministic ICP
# filter runs BEFORE the LLM, so off-ICP commenters (the bulk of a viral thread) cost zero
# tokens regardless. Env-tunable for cheaper runs.
COMMENT_LIMIT = int(os.environ.get("APIFY_COMMENT_LIMIT", "150"))


def extract_demo() -> list[Commenter]:
    with open(_DEMO_COMMENTS, "r", encoding="utf-8") as fh:
        return [Commenter(**row) for row in json.load(fh)]


def _map_comment(raw: dict, post_url: Optional[str]) -> Optional[Commenter]:
    """Map one Apify comment record to a Commenter. Returns None if no comment text.

    Handles the harvestapi shape (commentary + nested actor) and falls back to the
    flatter field names other comment actors use.
    """
    text = (
        raw.get("commentary")
        or raw.get("commentText")
        or raw.get("text")
        or raw.get("comment")
    )
    if not text or not str(text).strip():
        return None

    actor = raw.get("actor") or raw.get("author")
    if isinstance(actor, dict):
        name = (
            actor.get("name")
            or " ".join(p for p in (actor.get("firstName"), actor.get("lastName")) if p)
            or actor.get("fullName")
            or "unknown"
        )
        headline = actor.get("headline") or actor.get("position") or actor.get("occupation")
        profile_url = actor.get("linkedinUrl") or actor.get("profileUrl") or actor.get("url")
        company = _company(actor)
    else:
        name = actor or raw.get("name") or "unknown"
        headline = raw.get("headline") or raw.get("occupation")
        profile_url = raw.get("profileUrl") or raw.get("profile_url") or raw.get("url")
        company = _company_from_headline(headline)

    reactions = (raw.get("engagement") or {}).get("reactions")
    reaction = reactions[0].get("type") if isinstance(reactions, list) and reactions else raw.get("reactionType")

    return Commenter(
        name=name,
        headline=headline,
        company=company,
        profile_url=profile_url,
        comment_text=str(text).strip(),
        reaction=reaction,
        timestamp=raw.get("createdAt") or raw.get("timestamp"),
        # Every surfaced lead needs a post link for the rep. Prefer an explicit postUrl,
        # then the post being scraped, then reconstruct from the comment's postId urn so a
        # multi-post extract (default_post=None) still yields a working link -- never "n/a".
        post_url=raw.get("postUrl") or post_url or _post_url_from_id(raw.get("postId")),
        source="live",
    )


def _post_url_from_id(post_id: Optional[str]) -> Optional[str]:
    """Reconstruct a canonical post URL from the comment record's activity urn/id."""
    if not post_id:
        return None
    pid = str(post_id).strip()
    # accept 'urn:li:activity:123', 'activity:123', or a bare numeric id
    urn = pid if pid.startswith("urn:li:activity:") else f"urn:li:activity:{pid.split(':')[-1]}"
    return f"https://www.linkedin.com/feed/update/{urn}"


def _is_author(raw: dict) -> bool:
    actor = raw.get("actor")
    return isinstance(actor, dict) and bool(actor.get("author"))


def map_raw_items(raw_items: list[dict], default_post: Optional[str] = None) -> list[Commenter]:
    """Map raw Apify records to Commenters, dropping the post author and deduping
    to one lead per person (keeping their longest comment -- the most signal).

    Pure transform, so the same logic runs on a fresh scrape or a cached raw file.
    """
    mapped: list[Commenter] = []
    for raw in raw_items:
        if _is_author(raw):
            continue  # the post author replying to their own thread is not a lead
        c = _map_comment(raw, default_post)
        if c:
            mapped.append(c)
        for reply in raw.get("replies", []) or []:
            if _is_author(reply):
                continue
            r = _map_comment(reply, raw.get("postUrl") or default_post)
            if r:
                mapped.append(r)

    # dedupe by profile_url, keeping the longest comment per person
    best: dict[str, Commenter] = {}
    no_url: list[Commenter] = []
    for c in mapped:
        if not c.profile_url:
            no_url.append(c)
            continue
        prev = best.get(c.profile_url)
        if prev is None or len(c.comment_text) > len(prev.comment_text):
            best[c.profile_url] = c
    return list(best.values()) + no_url


def reset_live_output() -> None:
    """Truncate the raw-scrape file at the start of a run so it accumulates cleanly."""
    with open(_LIVE_OUT, "w", encoding="utf-8") as fh:
        json.dump([], fh)


def extract_live(post_urls: list[str]) -> list[Commenter]:
    body = {
        "posts": post_urls,
        "maxItems": COMMENT_LIMIT,
        "scrapeReplies": True,
        "profileScraperMode": "main",  # need headline + profileUrl for the title filter
    }
    raw_items = run_actor(APIFY_ACTOR, body)

    # provenance: ACCUMULATE the raw scrape locally (gitignored), never committed --
    # extract runs per post, so append rather than overwrite to keep the whole run.
    existing = []
    if os.path.exists(_LIVE_OUT):
        try:
            with open(_LIVE_OUT, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            existing = []
    with open(_LIVE_OUT, "w", encoding="utf-8") as fh:
        json.dump(existing + raw_items, fh, indent=2)

    default_post = post_urls[0] if len(post_urls) == 1 else None
    return map_raw_items(raw_items, default_post)


def extract_for_post(post: dict, mode: str) -> list[Commenter]:
    """Commenters on ONE post -- so each carries its post's type unambiguously."""
    if mode == "live":
        return extract_live([post["url"]])
    return [c for c in extract_demo() if c.post_url == post["url"]]


def extract(mode: str, posts: list[dict]) -> list[Commenter]:
    out: list[Commenter] = []
    for p in posts:
        out.extend(extract_for_post(p, mode))
    return out
