"""HYGIENE stage: CRM hygiene as a byproduct of the scrape.

Figma's stated GTM pain is stale Salesforce contacts -- years of people who changed
jobs or titles. The scraper already sees each commenter's CURRENT title and company, so
diffing that against the SFDC contact record flags stale CRM data for FREE. Deterministic,
zero tokens, runs on every lead.

HARD RULE (see CLAUDE.md): hygiene NEVER affects lead scoring or routing. It is a parallel
output -- flags go to a review queue (data/hygiene_queue.jsonl) and a compact Slack digest,
never an auto-overwrite. A human confirms before any SFDC write.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from functools import lru_cache

from schema import Commenter, HygieneFlag, HygieneStatus, Lead

_CONTACTS = os.path.join(os.path.dirname(__file__), "data", "sfdc_contacts.json")
_QUEUE = os.path.join(os.path.dirname(__file__), "data", "hygiene_queue.jsonl")

_LEGAL = {"inc", "inc.", "llc", "ltd", "ltd.", "co", "co.", "corp", "corp.", "gmbh", "plc", "the"}


def _norm(s: str | None) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in _LEGAL)


def _norm_url(u: str | None) -> str:
    return (u or "").split("?")[0].rstrip("/").lower()


def _title_from_headline(headline: str | None) -> str:
    """Best-effort CURRENT title from a LinkedIn headline ('Design Lead at Acme' -> 'Design Lead')."""
    h = (headline or "").strip()
    if not h:
        return ""
    low = h.lower()
    best = len(h)
    for sep in (" at ", " @ ", " | ", " - "):
        i = low.find(sep)
        if i != -1:
            best = min(best, i)
    return h[:best].strip()


@lru_cache(maxsize=1)
def _contacts() -> list[dict]:
    with open(_CONTACTS, "r", encoding="utf-8") as fh:
        return json.load(fh)["contacts"]


def _find(commenter: Commenter) -> dict | None:
    """Match the scraped commenter to an SFDC contact: by linkedin_url first, then name."""
    url = _norm_url(commenter.profile_url)
    if url:
        for c in _contacts():
            if _norm_url(c.get("linkedin_url")) == url:
                return c
    name = _norm(commenter.name)
    if name:
        for c in _contacts():
            if _norm(c.get("name")) == name:
                return c
    return None


def check(commenter: Commenter, mode: str = "demo") -> HygieneFlag:
    """Diff the scraped profile against the SFDC contact -> a HygieneFlag. Zero tokens.

    In live mode this is where the Salesforce Contact query goes; until wired it reads the
    synthetic fixture and labels the source, so nothing reads as real CRM data.
    """
    src = "demo" if mode != "live" else "demo-fallback"
    scraped_company = commenter.company
    scraped_title = _title_from_headline(commenter.headline)
    rec = _find(commenter)
    if not rec:
        return HygieneFlag(
            status=HygieneStatus.no_record, detail="not in Salesforce (net-new contact)",
            scraped_company=scraped_company, scraped_title=scraped_title, source=src,
        )
    sfdc_company, sfdc_title = rec.get("sfdc_company"), rec.get("sfdc_title")
    base = dict(
        contact_id=rec.get("contact_id"), sfdc_company=sfdc_company, sfdc_title=sfdc_title,
        scraped_company=scraped_company, scraped_title=scraped_title, source=src,
    )
    if scraped_company and sfdc_company and _norm(scraped_company) != _norm(sfdc_company):
        return HygieneFlag(status=HygieneStatus.job_change,
                           detail=f"company: SFDC '{sfdc_company}' -> now '{scraped_company}'", **base)
    if scraped_title and sfdc_title and _norm(scraped_title) != _norm(sfdc_title):
        return HygieneFlag(status=HygieneStatus.title_stale,
                           detail=f"title: SFDC '{sfdc_title}' -> now '{scraped_title}'", **base)
    return HygieneFlag(status=HygieneStatus.current, detail="SFDC matches scraped profile", **base)


def stale_flags(leads: list[Lead]) -> list[Lead]:
    return [l for l in leads if l.hygiene and l.hygiene.is_stale]


def counts(leads: list[Lead]) -> dict:
    c = Counter(l.hygiene.status.value for l in leads if l.hygiene)
    return {k: c.get(k, 0) for k in ("job_change", "title_stale", "no_record", "current")}


def append_queue(leads: list[Lead], timestamp: str | None = None) -> list[dict]:
    """Append stale flags to the review queue (gitignored). Never auto-overwrites SFDC."""
    rows = []
    for l in stale_flags(leads):
        h = l.hygiene
        rows.append({
            "timestamp": timestamp, "name": l.commenter.name, "profile_url": l.commenter.profile_url,
            "contact_id": h.contact_id, "status": h.status.value, "detail": h.detail,
            "sfdc_company": h.sfdc_company, "scraped_company": h.scraped_company,
            "sfdc_title": h.sfdc_title, "scraped_title": h.scraped_title,
            "confirmed": False,  # a human confirms before any SFDC write
        })
    if rows:
        with open(_QUEUE, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return rows


def build_digest(leads: list[Lead]) -> str | None:
    """ONE compact Slack digest per run (not one message per flag), or None if nothing stale."""
    stale = stale_flags(leads)
    if not stale:
        return None
    jc = sum(1 for l in stale if l.hygiene.status == HygieneStatus.job_change)
    ts = sum(1 for l in stale if l.hygiene.status == HygieneStatus.title_stale)
    head = (f"*CRM hygiene* -- {len(stale)} stale Salesforce record(s): "
            f"{jc} job change{'' if jc == 1 else 's'}, {ts} title mismatch{'' if ts == 1 else 'es'}. "
            f"Queued for review; no auto-writes.")
    lines = [head] + [f"  - {l.commenter.name} ({l.hygiene.contact_id}): {l.hygiene.detail}" for l in stale]
    return "\n".join(lines)
