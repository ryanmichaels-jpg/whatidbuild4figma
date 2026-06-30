"""Code-orchestrated pipeline. The LLM is one bounded step inside it.

DISCOVER -> EXTRACT -> FILTER (deterministic ICP) -> CLASSIFY (haiku, schema-bound)
-> GATE (verbatim quote required) -> NOTIFY -> DASHBOARD.

Run:  MODE=demo python pipeline.py   (zero credentials, uses committed fixtures)
      MODE=live python pipeline.py   (needs APIFY_TOKEN / FIRECRAWL_API_KEY / ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter

import accounts as accounts_mod
import classify as classify_mod
import discover as discover_mod
import extract as extract_mod
import posttype as posttype_mod
from gate import decide
from notify import notify
from schema import Commenter, Decision, Lead, PostType, TitleStatus
from verify import verify
from titles import classify_title

_GOLDEN = os.path.join(os.path.dirname(__file__), "data", "golden.json")


def process(commenter: Commenter, post_type: PostType | None, mode: str) -> Lead:
    """Run one commenter through filter -> (classify) -> gate -> verify -> account match + route."""
    title = classify_title(commenter.headline)
    cls = None
    quality_flag = None

    if title.status in (TitleStatus.excluded, TitleStatus.off_icp):
        decision = Decision.drop
        reason = (
            f"off-ICP title ({title.matched_keyword})"
            if title.status == TitleStatus.excluded
            else "title present but not a buyer/user persona"
        )
    elif title.status == TitleStatus.missing:
        decision = Decision.review
        reason = "missing title -- routed to human review, not dropped"
    else:
        # matched persona -> spend an LLM call, conditioned on the post type
        cls = classify_mod.classify(commenter, mode, post_type.value if post_type else None)
        decision, reason = decide(commenter, title, cls)

    lead = Lead(
        commenter=commenter, title=title, classification=cls,
        decision=decision, reason=reason, post_type=post_type,
    )

    # quality check: downgrade a surfaced lead whose evidence reads as praise, not intent
    new_decision, quality_flag = verify(lead)
    if new_decision != decision:
        lead.decision = new_decision
        lead.reason = quality_flag
        lead.quality_flag = quality_flag
        decision = new_decision

    # account match + expansion routing only for actionable leads (no CRM lookup on dropped noise)
    if decision in (Decision.surface, Decision.review):
        intent = cls.intent_type if cls else None
        account = accounts_mod.match_account(commenter.company, mode)
        lead.account = account
        lead.routing = accounts_mod.route(intent, account, commenter.company)
        from richness import score_richness

        lead.richness, lead.richness_label = score_richness(commenter.comment_text)

    return lead


_LEADS_JSON = os.path.join(os.path.dirname(__file__), "data", "leads-live.json")
_LEADS_CSV = os.path.join(os.path.dirname(__file__), "data", "leads-live.csv")


def _lead_record(lead: Lead) -> dict:
    c, cls, r = lead.commenter, lead.classification, lead.routing
    return {
        "decision": lead.decision.value,
        "richness": lead.richness_label or "",
        "name": c.name,
        "headline": (c.headline or "").replace("\n", " "),
        "company": c.company or "",
        "persona": lead.title.persona.value if lead.title.persona else "",
        "intent": cls.intent_type.value if cls else "",
        "confidence": cls.confidence if cls else "",
        "post_type": lead.post_type.value if lead.post_type else "",
        "signal": r.signal_type.value if r else "",
        "route": r.recipient if r else "",
        "reason": lead.reason,
        "evidence_quote": cls.evidence_quote if cls else "",
        "comment": " ".join(c.comment_text.split()),
        "profile_url": c.profile_url or "",
        "post_url": c.post_url or "",
    }


def dump_leads(leads: list[Lead]) -> str:
    """Persist EVERY lead (the full run output) to gitignored JSON + CSV."""
    order = {"surface": 0, "review": 1, "drop": 2}
    records = sorted((_lead_record(x) for x in leads), key=lambda r: order.get(r["decision"], 9))
    with open(_LEADS_JSON, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    if records:
        with open(_LEADS_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)
    return _LEADS_CSV


def run_with_posts(mode: str | None = None):
    """Full pipeline. Returns (leads, post_results-by-url)."""
    mode = mode or os.environ.get("MODE", "demo")
    if mode == "live":
        extract_mod.reset_live_output()
    posts = discover_mod.discover(mode)

    # POST-TYPE GATE: classify every post; only mine the qualifying types.
    post_results = {p["url"]: posttype_mod.classify_post(p, mode) for p in posts}

    leads: list[Lead] = []
    for post in posts:
        pc = post_results[post["url"]]
        if not pc.qualifies:
            continue  # off_topic / showcase -> never scrape its comments
        for commenter in extract_mod.extract_for_post(post, mode):
            leads.append(process(commenter, pc.post_type, mode))
    return leads, post_results


def run(mode: str | None = None) -> list[Lead]:
    return run_with_posts(mode)[0]


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


def _load_golden() -> dict | None:
    try:
        with open(_GOLDEN, "r", encoding="utf-8") as fh:
            return {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    except FileNotFoundError:
        return None


def main() -> None:
    import datetime

    import monitoring

    mode = os.environ.get("MODE", "demo")
    leads, post_results = run_with_posts(mode)

    metrics = monitoring.compute(leads, post_results, _load_golden())
    print(f"mode={mode}  metrics={metrics}")

    for lead in leads:
        if lead.decision == Decision.surface:
            notify(lead)

    monitoring.append_run_log(metrics, mode, datetime.datetime.utcnow().isoformat() + "Z")

    leads_out = dump_leads(leads)
    print(f"leads ({len(leads)}) -> {leads_out}")

    from dashboard import render

    out = render(leads, mode, post_results)
    print(f"dashboard -> {out}")


if __name__ == "__main__":
    main()
