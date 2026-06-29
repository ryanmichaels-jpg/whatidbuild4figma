import json
import os

from pipeline import funnel, precision_vs_golden, run
from schema import Decision

_GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "golden.json")


def _golden():
    with open(_GOLDEN, "r", encoding="utf-8") as fh:
        return {k: v for k, v in json.load(fh).items() if not k.startswith("_")}


def test_demo_matches_golden_exactly():
    leads = run("demo")
    golden = _golden()
    by_url = {x.commenter.profile_url: x.decision.value for x in leads}
    for url, expected in golden.items():
        assert by_url[url] == expected, f"{url}: got {by_url[url]}, expected {expected}"


def test_demo_funnel_counts():
    leads = run("demo")
    f = funnel(leads)
    assert f["extracted"] == 13
    assert f["surfaced"] == 3
    assert f["review"] == 4  # includes the builder/prospect routed to review
    assert f["dropped"] == 6


def test_off_icp_never_reaches_the_llm():
    # dropped/excluded/missing leads must have no classification (no tokens spent)
    leads = run("demo")
    for x in leads:
        if x.decision == Decision.drop and "verbatim" not in x.reason and "noise" not in x.reason:
            assert x.classification is None


def test_every_surfaced_lead_has_verbatim_evidence():
    leads = run("demo")
    for x in leads:
        if x.decision == Decision.surface:
            assert x.classification.evidence_quote in x.commenter.comment_text


def test_eval_is_perfect_on_golden():
    leads = run("demo")
    prec = precision_vs_golden(leads)
    assert prec["accuracy"] == 1.0
    assert prec["surface_precision"] == 1.0
