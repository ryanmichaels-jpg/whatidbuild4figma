"""DISCOVER stage: find LinkedIn intent-post URLs.

Apify-only: demo mode reads committed synthetic posts; live mode runs an Apify
LinkedIn post-search actor (slug from APIFY_POST_SEARCH_ACTOR) over the intent
keywords. Keeping discovery and extraction on a single provider means one
credential and one configurable, auditable scraping source.
"""
from __future__ import annotations

import json
import os
from typing import Optional

INTENT_KEYWORDS = [
    "Figma alternative",
    "replacing Figma",
    "leaving Figma",
    "ditching Figma",
    "comment and I'll send the guide",
    "what are you using instead of Figma",
]

_DEMO_POSTS = os.path.join(os.path.dirname(__file__), "data", "demo_posts.json")

APIFY_BASE = "https://api.apify.com/v2/acts"
APIFY_POST_SEARCH_ACTOR = os.environ.get(
    "APIFY_POST_SEARCH_ACTOR", "curious_coder~linkedin-post-search-scraper"
)


def discover_demo() -> list[dict]:
    with open(_DEMO_POSTS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def discover_live(keywords: Optional[list[str]] = None, limit: int = 10) -> list[dict]:
    import requests

    keywords = keywords or INTENT_KEYWORDS
    token = os.environ["APIFY_TOKEN"]
    actor = APIFY_POST_SEARCH_ACTOR.replace("/", "~")
    url = f"{APIFY_BASE}/{actor}/run-sync-get-dataset-items?token={token}"
    body = {"queries": keywords, "maxItems": limit}
    resp = requests.post(url, json=body, timeout=180)
    resp.raise_for_status()

    seen, posts = set(), []
    for it in resp.json():
        post_url = it.get("url") or it.get("postUrl") or it.get("link")
        if post_url and post_url not in seen:
            seen.add(post_url)
            posts.append({"url": post_url, "title": it.get("text") or it.get("title") or "", "keyword": None})
    return posts


def discover(mode: str, **kwargs) -> list[dict]:
    return discover_live(**kwargs) if mode == "live" else discover_demo()
