"""ADOPTION FEEDBACK: reps are the labeling function.

We already measure precision vs a golden set. This closes the OTHER loop the JD asks for:
do reps actually ACT on what we surface? Each Slack card carries a reaction footer
(booked / bad_lead / wrong_route); this module collects those reactions, attaches
`rep_action` to the lead, and:
  - persists per-lead feedback to data/feedback.jsonl (gitignored),
  - feeds the top-line ADOPTION metric (acted / surfaced) into the run log + dashboard,
  - appends 👎 leads to data/golden_candidates.jsonl for review + eventual promotion into
    golden.json.

The loop: reps label production data -> golden set grows -> precision measurement improves
-> gates get retuned. Closing that loop is the point.

Pluggable backend so demo runs with no keys:
  - `demo`      -> reads data/feedback_sim.jsonl (a realistic sample).
  - `slack_api` -> real reactions.get flow (documented, stubbed; needs SLACK_BOT_TOKEN).
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from schema import Lead

_SIM = os.path.join(os.path.dirname(__file__), "data", "feedback_sim.jsonl")
_FEEDBACK = os.path.join(os.path.dirname(__file__), "data", "feedback.jsonl")
_GOLDEN_CAND = os.path.join(os.path.dirname(__file__), "data", "golden_candidates.jsonl")

ACTIONS = ("booked", "bad_lead", "wrong_route", "none")
ACTED = {"booked", "bad_lead", "wrong_route"}  # any reaction == the rep acted on it


def _backend(mode: str) -> str:
    return os.environ.get("FEEDBACK_BACKEND", "demo" if mode != "live" else "slack_api")


def collect(mode: str = "demo") -> dict[str, str]:
    """Return {profile_url: rep_action}. Pluggable; demo reads a sim file, zero keys."""
    if _backend(mode) == "slack_api":
        return _collect_slack_api()
    return _collect_demo()


def _collect_demo() -> dict[str, str]:
    if not os.path.exists(_SIM):
        return {}
    out: dict[str, str] = {}
    with open(_SIM, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                if r.get("rep_action") in ACTIONS:
                    out[r["profile_url"]] = r["rep_action"]
    return out


def _collect_slack_api() -> dict[str, str]:
    """Real path (documented, not required for demo): map each surfaced lead's stored Slack
    message ts -> reactions via `reactions.get`, then emoji -> action:
        white_check_mark/calendar -> booked, -1 -> bad_lead, repeat/twisted_rightwards_arrows -> wrong_route.
    Needs SLACK_BOT_TOKEN + a persisted message-ts map. Returns {} when unconfigured so the
    pipeline never breaks.
    """
    if not os.environ.get("SLACK_BOT_TOKEN"):
        return {}
    raise NotImplementedError(
        "Slack reactions.get flow not wired; set SLACK_BOT_TOKEN and map message ts -> lead."
    )


def apply(leads: list[Lead], mode: str = "demo", timestamp: str | None = None) -> dict:
    """Attach rep_action to surfaced leads, persist feedback, grow golden candidates.

    Returns aggregates (top-line adoption + segment action rates). Never changes routing.
    """
    fb = collect(mode)
    surfaced = [l for l in leads if l.decision.value == "surface"]
    rows, cand_rows = [], []
    for l in surfaced:
        action = fb.get(l.commenter.profile_url or "", "none")
        l.rep_action = action
        rows.append({
            "timestamp": timestamp, "profile_url": l.commenter.profile_url,
            "name": l.commenter.name, "rep_action": action,
            "figma_surface": l.figma_surface.value if l.figma_surface else None,
            "post_type": l.post_type.value if l.post_type else None,
        })
        # a thumbs-down is a labeled negative: candidate for the golden set
        if action == "bad_lead":
            cand_rows.append({
                "timestamp": timestamp, "profile_url": l.commenter.profile_url,
                "name": l.commenter.name, "label": "drop", "reason": "rep marked bad_lead",
                "evidence_quote": l.classification.evidence_quote if l.classification else None,
            })
    _append(_FEEDBACK, rows)
    _append(_GOLDEN_CAND, cand_rows)
    return aggregate(surfaced)


def aggregate(surfaced: list[Lead]) -> dict:
    n = len(surfaced)
    acted = sum(1 for l in surfaced if (l.rep_action or "none") in ACTED)
    by_action = Counter(l.rep_action or "none" for l in surfaced)

    def _rate(group):
        seg = defaultdict(lambda: [0, 0])  # key -> [acted, total]
        for l in surfaced:
            k = group(l)
            seg[k][1] += 1
            if (l.rep_action or "none") in ACTED:
                seg[k][0] += 1
        return {k: {"acted": a, "total": t, "rate": round(a / t, 3) if t else None} for k, (a, t) in seg.items()}

    return {
        "surfaced": n,
        "acted": acted,
        "rep_action_rate": round(acted / n, 3) if n else None,
        "by_action": {k: by_action.get(k, 0) for k in ACTIONS},
        "by_figma_surface": _rate(lambda l: l.figma_surface.value if l.figma_surface else "none"),
        "by_post_type": _rate(lambda l: l.post_type.value if l.post_type else "none"),
    }


def _append(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
