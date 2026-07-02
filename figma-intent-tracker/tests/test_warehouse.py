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
