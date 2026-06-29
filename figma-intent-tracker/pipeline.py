"""Code-orchestrated pipeline. The LLM is one bounded step inside it.

DISCOVER -> EXTRACT -> FILTER (deterministic ICP) -> CLASSIFY (haiku, schema-bound)
-> GATE (verbatim quote required) -> NOTIFY -> DASHBOARD.

Run:  MODE=demo python pipeline.py   (zero credentials, uses committed fixtures)
      MODE=live python pipeline.py   (needs APIFY_TOKEN / FIRECRAWL_API_KEY / ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import json
import os
from collections import Counter

import classify as classify_mod
import discover as discover_mod
import extract as extract_mod
from gate import decide
from notify import notify
from schema import Commenter, Decision, Lead, TitleStatus
from titles import classify_title

_GOLDEN = os.path.join(os.path.dirname(__file__), "data", "golden.json")


def process(commenter: Commenter, mode: str) -> Lead:
    """Run one commenter through filter -> (classify) -> gate."""
    title = classify_title(commenter.headline)

    if title.status in (TitleStatus.excluded, TitleStatus.off_icp):
        reason = (
            f"off-ICP title ({title.matched_keyword})"
            if title.status == TitleStatus.excluded
            else "title present but not a buyer/user persona"
        )
        return Lead(commenter=commenter, title=title, decision=Decision.drop, reason=reason)

    if title.status == TitleStatus.missing:
        return Lead(
            commenter=commenter,
            title=title,
            decision=Decision.review,
            reason="missing title -- routed to human review, not dropped",
        )

    # matched persona -> spend an LLM call
    cls = classify_mod.classify(commenter, mode)
    decision, reason = decide(commenter, title, cls)
    return Lead(commenter=commenter, title=title, classification=cls, decision=decision, reason=reason)


def run(mode: str | None = None) -> list[Lead]:
    mode = mode or os.environ.get("MODE", "demo")
    posts = discover_mod.discover(mode)
    commenters = extract_mod.extract(mode, posts)
    return [process(c, mode) for c in commenters]


def funnel(leads: list[Lead]) -> dict:
    title_passed = sum(1 for x in leads if x.title.status == TitleStatus.matched)
    classified = sum(1 for x in leads if x.classification is not None)
    decisions = Counter(x.decision.value for x in leads)
    return {
        "extracted": len(leads),
        "title_filtered_in": title_passed,
        "classified": classified,
        "surfaced": decisions.get("surface", 0),
        "review": decisions.get("review", 0),
        "dropped": decisions.get("drop", 0),
    }


def precision_vs_golden(leads: list[Lead]) -> dict | None:
    """Compare decisions to the golden labels (demo). Returns None if no golden file applies."""
    try:
        with open(_GOLDEN, "r", encoding="utf-8") as fh:
            golden = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    except FileNotFoundError:
        return None
    matched = [x for x in leads if x.commenter.profile_url in golden]
    if not matched:
        return None
    correct = sum(1 for x in matched if x.decision.value == golden[x.commenter.profile_url])
    surfaced = [x for x in matched if x.decision == Decision.surface]
    surf_tp = sum(1 for x in surfaced if golden[x.commenter.profile_url] == "surface")
    return {
        "labeled": len(matched),
        "accuracy": round(correct / len(matched), 3),
        "surface_precision": round(surf_tp / len(surfaced), 3) if surfaced else None,
    }


def main() -> None:
    mode = os.environ.get("MODE", "demo")
    leads = run(mode)

    f = funnel(leads)
    print(f"mode={mode}  funnel={f}")

    for lead in leads:
        if lead.decision == Decision.surface:
            notify(lead)

    prec = precision_vs_golden(leads)
    if prec:
        print(f"eval={prec}")

    from dashboard import render

    out = render(leads, mode)
    print(f"dashboard -> {out}")


if __name__ == "__main__":
    main()
