"""DISCOVER stage: find LinkedIn intent-post URLs.

Apify-only and cookie-free: live mode runs the Apify Google Search Scraper over
`site:linkedin.com/posts "<keyword>"` queries and keeps the LinkedIn post URLs it
returns. This avoids needing a LinkedIn session cookie just to discover posts --
the cookie is only required downstream for authenticated comment extraction.
Demo mode reads committed synthetic posts. Actor slug is env-configurable.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from apify_run import run_actor

INTENT_KEYWORDS = [
    "Figma alternative",
    "replacing Figma",
    "leaving Figma",
    "ditching Figma",
    "comment and I'll send the guide",
    "what are you using instead of Figma",
]

_DEMO_POSTS = os.path.join(os.path.dirname(__file__), "data", "demo_posts.json")

# Cookie-free discovery. Override with an authenticated LinkedIn post-search actor if preferred.
APIFY_POST_SEARCH_ACTOR = os.environ.get("APIFY_POST_SEARCH_ACTOR", "apify~google-search-scraper")


def discover_demo() -> list[dict]:
    with open(_DEMO_POSTS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _post_url(url: str) -> bool:
    return "linkedin.com/posts/" in url


def discover_live(keywords: Optional[list[str]] = None, limit: int = 10) -> list[dict]:
    keywords = keywords or INTENT_KEYWORDS
    queries = "\n".join(f'site:linkedin.com/posts "{kw}"' for kw in keywords)
    body = {
        "queries": queries,
        "resultsPerPage": limit,
        "maxPagesPerQuery": 1,
        "countryCode": "us",
    }
    items = run_actor(APIFY_POST_SEARCH_ACTOR, body)

    seen, posts = set(), []
    for item in items:
        for row in item.get("organicResults", []) or []:
            url = (row.get("url") or "").split("?")[0]
            if url and _post_url(url) and url not in seen:
                seen.add(url)
                posts.append({"url": url, "title": row.get("title") or row.get("description") or "", "keyword": None})
    return posts


def discover(mode: str, **kwargs) -> list[dict]:
    return discover_live(**kwargs) if mode == "live" else discover_demo()
