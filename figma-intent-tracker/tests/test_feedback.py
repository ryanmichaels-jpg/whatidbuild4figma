import feedback
from schema import Commenter, Classification, Decision, FigmaSurface, IntentType, Lead, PostType, TitleResult, TitleStatus


def _lead(profile, action=None, surface=FigmaSurface.sites, decision=Decision.surface):
    l = Lead(
        commenter=Commenter(name="X", profile_url=profile, comment_text="c", source="demo"),
        title=TitleResult(status=TitleStatus.matched), decision=decision, reason="r",
        post_type=PostType.lead_magnet, figma_surface=surface,
        classification=Classification(intent_type=IntentType.active_need, need="n",
                                       evidence_quote="q", confidence=0.9, suggested_angle="a"),
    )
    l.rep_action = action
    return l


def test_aggregate_action_rate_and_breakdown():
    leads = [
        _lead("a", "booked"), _lead("b", "booked"),
        _lead("c", "none"), _lead("d", "bad_lead"), _lead("e", "wrong_route"),
    ]
    agg = feedback.aggregate(leads)
    assert agg["surfaced"] == 5
    assert agg["acted"] == 4                      # booked+bad_lead+wrong_route
    assert agg["rep_action_rate"] == 0.8
    assert agg["by_action"]["booked"] == 2 and agg["by_action"]["none"] == 1


def test_per_surface_rate():
    leads = [
        _lead("a", "booked", FigmaSurface.sites),
        _lead("b", "none", FigmaSurface.sites),
        _lead("c", "booked", FigmaSurface.motion),
    ]
    agg = feedback.aggregate(leads)
    assert agg["by_figma_surface"]["sites"] == {"acted": 1, "total": 2, "rate": 0.5}
    assert agg["by_figma_surface"]["motion"]["rate"] == 1.0


def test_collect_demo_reads_sim_file():
    fb = feedback.collect("demo")
    # sim file maps the demo surfaced leads
    assert fb.get("https://www.linkedin.com/in/demo-maya-chen") == "booked"
    assert fb.get("https://www.linkedin.com/in/demo-priya-nair") == "bad_lead"


def test_apply_attaches_action_and_flags_bad_lead(tmp_path, monkeypatch):
    # redirect the append files so the test doesn't touch real data
    monkeypatch.setattr(feedback, "_FEEDBACK", str(tmp_path / "fb.jsonl"))
    monkeypatch.setattr(feedback, "_GOLDEN_CAND", str(tmp_path / "gc.jsonl"))
    leads = [
        _lead("https://www.linkedin.com/in/demo-maya-chen"),   # booked in sim
        _lead("https://www.linkedin.com/in/demo-priya-nair"),  # bad_lead in sim
    ]
    agg = feedback.apply(leads, "demo")
    assert leads[0].rep_action == "booked" and leads[1].rep_action == "bad_lead"
    assert agg["acted"] == 2
    gc = (tmp_path / "gc.jsonl").read_text()
    assert "demo-priya-nair" in gc and "drop" in gc   # 👎 became a golden candidate
