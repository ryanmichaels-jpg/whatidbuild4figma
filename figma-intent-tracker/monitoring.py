"""MONITORING: metrics over a run, plus an append-only run log for drift tracking.

Tracks the health of the trust layer rather than vanity counts: the post-type and
lead funnels, intent distribution, how many hallucinated quotes the gate killed, how
many praise-mislabels the verifier downgraded, and precision vs the golden set. The
run log lets these be charted over time so accuracy drift is visible.
"""
from __future__ import annotations

import json
import os
from collections import Counter

from schema import Decision, Lead, PostClassification

_RUN_LOG = os.path.join(os.path.dirname(__file__), "data", "run_log.jsonl")


def compute(leads: list[Lead], post_results: dict[str, PostClassification], golden: dict | None = None) -> dict:
    decisions = Counter(x.decision.value for x in leads)
    intents = Counter(
        x.classification.intent_type.value for x in leads if x.classification is not None
    )
    post_types = Counter(pc.post_type.value for pc in post_results.values())

    hallucinations = sum(1 for x in leads if "verbatim" in x.reason)
    verifier_downgrades = sum(1 for x in leads if x.quality_flag and x.quality_flag != "thin_handraise")

    m = {
        "posts_total": len(post_results),
        "posts_qualified": sum(1 for pc in post_results.values() if pc.qualifies),
        "post_types": dict(post_types),
        "commenters": len(leads),
        "surfaced": decisions.get("surface", 0),
        "review": decisions.get("review", 0),
        "dropped": decisions.get("drop", 0),
        "intent_distribution": dict(intents),
        "gate_hallucinations_caught": hallucinations,
        "verifier_downgrades": verifier_downgrades,
    }

    if golden:
        labeled = [x for x in leads if x.commenter.profile_url in golden]
        if labeled:
            correct = sum(1 for x in labeled if x.decision.value == golden[x.commenter.profile_url])
            m["eval_labeled"] = len(labeled)
            m["eval_accuracy"] = round(correct / len(labeled), 3)
            # per-intent precision: of leads the pipeline surfaced, how many golden agree
            surfaced = [x for x in labeled if x.decision == Decision.surface]
            tp = sum(1 for x in surfaced if golden[x.commenter.profile_url] == "surface")
            m["surface_precision"] = round(tp / len(surfaced), 3) if surfaced else None
    return m


def append_run_log(metrics: dict, mode: str, timestamp: str) -> str:
    """Append one run's metrics as a JSON line (gitignored). Caller supplies the timestamp."""
    record = {"timestamp": timestamp, "mode": mode, **metrics}
    with open(_RUN_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return _RUN_LOG


def load_run_log() -> list[dict]:
    if not os.path.exists(_RUN_LOG):
        return []
    with open(_RUN_LOG, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
