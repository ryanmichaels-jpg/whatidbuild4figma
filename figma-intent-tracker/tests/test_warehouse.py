import json
import os

import warehouse


def test_local_write_creates_partition(tmp_path, monkeypatch):
    monkeypatch.setattr(warehouse, "_ROOT", str(tmp_path))
    n = warehouse.write_table("t1", [{"a": 1}, {"a": 2}], "2026-07-02")
    assert n == 0
    part_dir = tmp_path / "t1" / "dt=2026-07-02"
    files = os.listdir(part_dir)
    assert files, "expected a part.* file"
    # jsonl fallback when pyarrow is absent
    if any(f.endswith(".jsonl") for f in files):
        rows = [json.loads(l) for l in open(part_dir / "part.jsonl")]
        assert rows == [{"a": 1}, {"a": 2}]


def test_empty_rows_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(warehouse, "_ROOT", str(tmp_path))
    assert warehouse.write_table("t2", [], "2026-07-02") == 0
    assert not os.path.exists(tmp_path / "t2")


def test_sink_failure_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(warehouse, "_ROOT", str(tmp_path))
    monkeypatch.setattr(warehouse, "_write_local", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    # returns 1 (an error), but does NOT raise -> the run can continue and Slack still delivers
    assert warehouse.write_table("t3", [{"a": 1}], "2026-07-02") == 1


def test_snowflake_backend_noops_without_connector(tmp_path, monkeypatch):
    monkeypatch.setattr(warehouse, "_ROOT", str(tmp_path))
    monkeypatch.setenv("WAREHOUSE_BACKEND", "snowflake")
    # no snowflake-connector installed in CI -> logged no-op, returns 0, never raises
    assert warehouse.write_table("t4", [{"a": 1}], "2026-07-02") == 0


# --- Section 2: table builders + validation ---
from warehouse import schemas as wsc
from schema import (Classification, Commenter, Decision, FigmaSurface, HygieneFlag, HygieneStatus,
                    IntentType, Lead, PostClassification, PostType, TitleResult, TitleStatus)


def _cls(quote="i need this"):
    return Classification(intent_type=IntentType.active_need, need="n", evidence_quote=quote,
                          confidence=0.9, suggested_angle="a")


def _lead(decision, cls=None, name="Jane", profile="p", surface=FigmaSurface.sites,
          hygiene=None, rep_action=None):
    l = Lead(commenter=Commenter(name=name, profile_url=profile, company="Acme",
                                 headline="Product Designer at Acme", comment_text="c", source="demo"),
             title=TitleResult(status=TitleStatus.matched), decision=decision, reason="r",
             classification=cls, post_type=PostType.tool_comparison, figma_surface=surface, hygiene=hygiene)
    l.rep_action = rep_action
    return l


def test_schema_validation_rejects_bad_rows():
    import pytest
    with pytest.raises(wsc.SchemaError):
        wsc.validate("rep_outcomes", [{"lead_id": "x", "rep_action": "booked"}])  # missing fields
    with pytest.raises(wsc.SchemaError):
        wsc.validate("rep_outcomes", [{"lead_id": "x", "rep_action": "booked",
                                       "opportunity_id": None, "run_date": 20260702}])  # wrong type
    with pytest.raises(wsc.SchemaError):
        wsc.validate("displaced_tool_trends", [{"run_date": "d", "displaced_tool": "webflow",
                     "figma_surface": "sites", "post_type": "x", "post_count": 1, "extra": 1}])  # extra field


def test_intent_events_inherit_the_gates():
    leads = [
        _lead(Decision.surface, _cls("i need this")),                       # survived -> in
        _lead(Decision.drop, _cls("hallucinated quote"), name="Ghost"),     # gate-failed -> out
        _lead(Decision.review, None, name="NoClass"),                       # never classified -> out
    ]
    rows = wsc.build_intent_events(leads, "2026-07-02")
    assert [r["person"] for r in rows] == ["Jane"]
    assert "Ghost" not in {r["person"] for r in rows}  # a hallucination is UNREPRESENTABLE


def test_trends_is_deidentified():
    pr = {
        "u1": PostClassification(post_type=PostType.tool_comparison, figma_surface=FigmaSurface.sites,
                                 qualifies=True, tools_mentioned=["Webflow"], reason="r"),
        "u2": PostClassification(post_type=PostType.showcase, figma_surface=FigmaSurface.none,
                                 qualifies=False, tools_mentioned=["Webflow"], reason="r"),  # a DISCARD, still counted
    }
    rows = wsc.build_displaced_tool_trends(pr, "2026-07-02")
    allowed = {"run_date", "displaced_tool", "figma_surface", "post_type", "post_count"}
    for r in rows:
        assert set(r) == allowed          # no name / url / quote fields anywhere
    assert sum(r["post_count"] for r in rows) == 2  # both posts counted, incl. the discard


def test_rep_outcomes_carry_lead_id_not_name():
    rows = wsc.build_rep_outcomes([_lead(Decision.surface, _cls(), rep_action="booked")], "2026-07-02")
    assert rows and "name" not in rows[0] and rows[0]["lead_id"] and rows[0]["rep_action"] == "booked"
