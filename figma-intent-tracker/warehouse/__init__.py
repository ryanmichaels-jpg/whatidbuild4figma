"""WAREHOUSE sink -- the pipeline is a sensor; Snowflake is institutional memory.

Slack gets the lead, Snowflake gets the memory. Everything the pipeline learns becomes a
queryable, partitioned table so RevOps / data science / PMM can join it -- that's what turns
a scraper into a GTM data asset.

Pluggable backend, same pattern as feedback.py:
  - `local` (default, no keys): parquet via pyarrow, JSONL fallback if pyarrow is absent,
    written to data/warehouse/<table>/dt=<run_date>/.
  - `snowflake` (documented stub): stage the partition, COPY INTO per table. Lazy import;
    no-ops with a logged warning if snowflake-connector isn't installed.

BEST-EFFORT INVARIANT: a sink failure must NEVER block Slack delivery or fail the run. Every
write is wrapped; failures are counted (returned to the caller as `warehouse_write_errors`)
and logged, and the run continues.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("warehouse")

_ROOT = os.path.join(os.path.dirname(__file__), os.pardir, "data", "warehouse")


def _backend() -> str:
    return os.environ.get("WAREHOUSE_BACKEND", "local")


def _partition_dir(table: str, run_date: str) -> str:
    d = os.path.join(_ROOT, table, f"dt={run_date}")
    os.makedirs(d, exist_ok=True)
    return d


def write_table(table: str, rows: list[dict], run_date: str) -> int:
    """Best-effort write of `rows` to <table>, partitioned by run_date.

    Returns 0 on success (or empty input), 1 if the write failed -- never raises, so a sink
    problem can't take down Slack delivery or the run.
    """
    if not rows:
        return 0
    try:
        if _backend() == "snowflake":
            return _write_snowflake(table, rows, run_date)
        return _write_local(table, rows, run_date)
    except Exception as e:  # best-effort: swallow, count, continue
        log.warning("warehouse write failed for table %s: %s", table, e)
        return 1


def _write_local(table: str, rows: list[dict], run_date: str) -> int:
    d = _partition_dir(table, run_date)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist(rows), os.path.join(d, "part.parquet"))
    except ImportError:
        with open(os.path.join(d, "part.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return 0


def _write_snowflake(table: str, rows: list[dict], run_date: str) -> int:
    """Production path (documented, stubbed). See WAREHOUSE.md.

    Real flow: write the partition locally, PUT it to the table's internal stage, then
    `COPY INTO <db>.<schema>.<table>` with MATCH_BY_COLUMN_NAME. Lazy import so this module
    imports with no dependency; a missing connector logs a warning and no-ops (returns 0).
    """
    try:
        import snowflake.connector  # noqa: F401
    except ImportError:
        log.warning("WAREHOUSE_BACKEND=snowflake but snowflake-connector is not installed; "
                    "skipping write for %s (install snowflake-connector-python to enable)", table)
        return 0
    raise NotImplementedError(
        "Snowflake COPY INTO not wired. Stage the partition and COPY INTO the table here."
    )
