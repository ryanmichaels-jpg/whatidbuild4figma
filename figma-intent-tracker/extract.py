"""EXTRACT stage: pull commenters from intent posts.

Demo mode reads committed synthetic commenters. Live mode calls an Apify LinkedIn
post-comments actor (slug from APIFY_ACTOR), maps its output onto the Commenter
trust-contract model, and writes the raw scrape to data/comments-live.json --
which is gitignored, so real people's data never lands in the repo.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from apify_run import run_actor
from schema import Commenter

_DEMO_COMMENTS = os.path.join(os.path.dirname(__file__), "data", "demo_comments.json")
_LIVE_OUT = os.path.join(os.path.dirname(__file__), "data", "comments-live.json")

APIFY_ACTOR = os.environ.get("APIFY_ACTOR", "scrapier~linkedin-post-comments-scraper")
# Authenticated extraction needs the operator's LinkedIn session cookie. Without it
# the actor runs but returns zero comments (LinkedIn has no public API).
LINKEDIN_LI_AT = os.environ.get("LINKEDIN_LI_AT", "")
RESULT_LIMIT_PER_POST = int(os.environ.get("APIFY_COMMENT_LIMIT", "30"))


def extract_demo() -> list[Commenter]:
    with open(_DEMO_COMMENTS, "r", encoding="utf-8") as fh:
        return [Commenter(**row) for row in json.load(fh)]


def _map_comment(raw: dict, post_url: Optional[str]) -> Optional[Commenter]:
    """Map one Apify comment record to a Commenter. Returns None if no comment text."""
    text = raw.get("commentText") or raw.get("text") or raw.get("comment")
    if not text or not str(text).strip():
        return None
    author = raw.get("author")
    if isinstance(author, dict):
        name = author.get("name") or author.get("fullName") or "unknown"
        headline = author.get("headline") or author.get("occupation")
        profile_url = author.get("profileUrl") or author.get("profile_url") or author.get("url")
    else:
        name = author or raw.get("name") or "unknown"
        headline = raw.get("headline") or raw.get("occupation")
        profile_url = raw.get("profileUrl") or raw.get("profile_url") or raw.get("url")
    return Commenter(
        name=name,
        headline=headline,
        profile_url=profile_url,
        comment_text=str(text).strip(),
        reaction=raw.get("reactionType") or raw.get("reaction"),
        timestamp=raw.get("timestamp") or raw.get("createdAt"),
        post_url=raw.get("postUrl") or post_url,
        source="live",
    )


def extract_live(post_urls: list[str]) -> list[Commenter]:
    body = {
        "startUrls": post_urls,
        "resultLimitPerPost": RESULT_LIMIT_PER_POST,
        "profileScraperMode": "full",  # need headline + profileUrl for the title filter
        "scrapeReplies": True,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    if LINKEDIN_LI_AT:
        body["liAt"] = LINKEDIN_LI_AT
    raw_items = run_actor(APIFY_ACTOR, body)

    # provenance: keep the raw scrape locally (gitignored), never committed
    with open(_LIVE_OUT, "w", encoding="utf-8") as fh:
        json.dump(raw_items, fh, indent=2)

    commenters = []
    for raw in raw_items:
        mapped = _map_comment(raw, post_urls[0] if len(post_urls) == 1 else None)
        if mapped:
            commenters.append(mapped)
        for reply in raw.get("replies", []) or []:
            mapped_reply = _map_comment(reply, raw.get("postUrl"))
            if mapped_reply:
                commenters.append(mapped_reply)
    return commenters


def extract(mode: str, posts: list[dict]) -> list[Commenter]:
    if mode == "live":
        return extract_live([p["url"] for p in posts])
    return extract_demo()
