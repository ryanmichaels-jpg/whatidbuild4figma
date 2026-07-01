import json
import os

from pipeline import funnel, precision_vs_golden, process, richness_lever, run, run_with_posts
from schema import Classification, Decision, IntentType, PostType
from titles import classify_title


def _cls(intent, conf):
    return Classification(intent_type=intent, need="n", evidence_quote="q", confidence=conf, suggested_angle="a")


def test_richness_lever_promotes_rich_review_holds_thin_surface():
    rich = _cls(IntentType.evaluating, 0.72)
    assert richness_lever(Decision.review, rich, "rich")[0] == Decision.surface   # promote
    assert richness_lever(Decision.surface, rich, "thin")[0] == Decision.review    # hold back
    assert richness_lever(Decision.review, rich, "moderate")[0] == Decision.review # moderate stays
    # curious is not surface-eligible, so richness can't promote it
    assert richness_lever(Decision.review, _cls(IntentType.curious, 0.9), "rich")[0] == Decision.review


def test_lead_magnet_handraise_surfaces_thin_icp():
    curious = _cls(IntentType.curious, 0.4)   # a one-word hand-raise reads as thin/curious
    icp = classify_title("Product Design Lead")   # matched, non-builder persona
    # thin hand-raise on a lead_magnet post surfaces + is flagged, from surface OR review
    dec, note, flag = richness_lever(Decision.surface, curious, "thin", PostType.lead_magnet, icp)
    assert dec == Decision.surface and flag == "thin_handraise"
    assert richness_lever(Decision.review, curious, "thin", PostType.lead_magnet, icp)[0] == Decision.surface
    # same thin comment on a tool_question post is still held for review (intent must be in the words there)
    assert richness_lever(Decision.surface, curious, "thin", PostType.tool_question, icp)[0] == Decision.review
    # praise on a bait post is engagement, not a hand-raise: verify flag blocks the promotion
    assert richness_lever(Decision.review, curious, "thin", PostType.lead_magnet, icp, "praise")[0] == Decision.review
    # a moderate tire-kicker on a lead_magnet post is NOT a thin hand-raise -> normal path
    assert richness_lever(Decision.review, curious, "moderate", PostType.lead_magnet, icp)[0] == Decision.review

def test_interaction_designer_now_matches():
    from titles import classify_title
    from schema import Persona, TitleStatus
    t = classify_title("Interaction Design and Product at Context&Co")
    assert t.status == TitleStatus.matched and t.persona == Persona.user


def test_design_adjacent_officp_routes_to_review_not_drop():
    from schema import Commenter, Decision, PostType
    # 'design' signal but no exact persona keyword -> off_icp, but design-adjacent
    c = Commenter(name="Test Person", headline="Design thinker & strategist",
                  comment_text="interesting", profile_url="https://x", source="demo")
    lead = process(c, PostType.lead_magnet, "demo")
    assert lead.decision == Decision.review          # not dropped
    assert lead.classification is None               # and no LLM tokens spent


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
    assert f["surfaced"] == 5  # rich builder promoted + thin ICP hand-raise on the lead-magnet post
    assert f["review"] == 2
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


def test_offtopic_post_is_dropped_before_mining():
    leads, post_results = run_with_posts("demo")
    off = post_results["https://www.linkedin.com/posts/demo-post-offtopic"]
    assert off.post_type == PostType.off_topic and not off.qualifies
    # the ICP designer who commented on the off-topic post never becomes a lead
    assert not any(l.commenter.name == "Pat Quinn" for l in leads)
    assert all(l.post_type in (PostType.lead_magnet, PostType.tool_question) for l in leads)
