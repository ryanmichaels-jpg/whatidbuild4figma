"""Warehouse table schemas + row builders. Each builder validates BEFORE the sink writes.

Five tables turn the run into institutional memory:
  - external_intent_events  : identified, gate-inherited intent (only leads that survived 07-09)
  - contact_observations    : CRM-hygiene observations for ALL leads (incl. non-ICP)
  - rep_outcomes            : adoption feedback, keyed by lead_id (no name)
  - run_telemetry           : one flattened row of run metrics (signal-quality metadata)
  - displaced_tool_trends   : DE-IDENTIFIED aggregate over all classified posts incl. discards

Schema = list of (field, python_type, nullable). validate() rejects missing/extra/mistyped/
null-in-non-nullable fields, so a malformed row can never reach the warehouse.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from schema import Decision, Lead, PostClassification

TABLES: dict[str, list[tuple]] = {
    "external_intent_events": [
        ("lead_id", str, False), ("person", str, False), ("company", str, False),
        ("figma_surface", str, False), ("recipe", str, False), ("post_type", str, False),
        ("intent_type", str, False), ("confidence", float, False), ("evidence_quote", str, False),
        ("source_url", str, False), ("route", str, False), ("priority", int, False),
        ("run_date", str, False),
    ],
    "contact_observations": [
        ("name", str, False), ("headline", str, False), ("company", str, False),
        ("sfdc_contact_id", str, True), ("flag", str, False), ("run_date", str, False),
    ],
    "rep_outcomes": [
        ("lead_id", str, False), ("rep_action", str, False),
        ("opportunity_id", str, True), ("run_date", str, False),
    ],
    "run_telemetry": [
        ("run_date", str, False), ("mode", str, False),
        ("posts_total", int, False), ("posts_qualified", int, False), ("commenters", int, False),
        ("surfaced", int, False), ("review", int, False), ("dropped", int, False),
        ("gate_hallucinations_caught", int, False), ("verifier_downgrades", int, False),
        ("eval_accuracy", float, True), ("surface_precision", float, True),
        ("rep_action_rate", float, True), ("warehouse_write_errors", int, False),
        ("by_recipe_json", str, False), ("by_lane_json", str, False),
        ("hygiene_json", str, False), ("intent_distribution_json", str, False),
    ],
    "displaced_tool_trends": [
        ("run_date", str, False), ("displaced_tool", str, False), ("figma_surface", str, False),
        ("post_type", str, False), ("post_count", int, False),
    ],
}


class SchemaError(ValueError):
    """A row did not match its table schema."""


def validate(table: str, rows: list[dict]) -> list[dict]:
    fields = {f: (t, n) for f, t, n in TABLES[table]}
    for i, row in enumerate(rows):
        extra = set(row) - set(fields)
        if extra:
            raise SchemaError(f"{table}[{i}]: unexpected field(s) {sorted(extra)}")
        for f, (t, nullable) in fields.items():
            if f not in row:
                raise SchemaError(f"{table}[{i}]: missing field '{f}'")
            v = row[f]
            if v is None:
                if not nullable:
                    raise SchemaError(f"{table}[{i}]: '{f}' is not nullable")
            elif not isinstance(v, t) or (t is not bool and isinstance(v, bool)):
                raise SchemaError(f"{table}[{i}]: '{f}' must be {t.__name__}, got {type(v).__name__}")
    return rows


def lead_id(lead: Lead) -> str:
    """Deterministic id for joins across tables -- not PII (a hash of profile + post)."""
    key = f"{lead.commenter.profile_url or ''}|{lead.commenter.post_url or ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def build_intent_events(leads: list[Lead], run_date: str) -> list[dict]:
    """GATE-INHERITED: only leads that survived gates 07-09 (decision == surface, with a
    verbatim-verified classification) can appear. A dropped/hallucinated lead is unrepresentable."""
    rows = []
    for l in leads:
        if l.decision != Decision.surface or l.classification is None:
            continue
        cls, r = l.classification, l.routing
        rows.append({
            "lead_id": lead_id(l), "person": l.commenter.name, "company": l.commenter.company or "",
            "figma_surface": l.figma_surface.value if l.figma_surface else "none",
            "recipe": l.recipe or "base_displacement",
            "post_type": l.post_type.value if l.post_type else "",
            "intent_type": cls.intent_type.value, "confidence": float(cls.confidence),
            "evidence_quote": cls.evidence_quote, "source_url": l.commenter.post_url or "",
            "route": r.recipient if r else "", "priority": r.priority if r else -1,
            "run_date": run_date,
        })
    return validate("external_intent_events", rows)


def build_contact_observations(leads: list[Lead], run_date: str) -> list[dict]:
    """ALL leads (incl. non-ICP) -- a job change is valuable regardless of ICP."""
    rows = []
    for l in leads:
        h = l.hygiene
        if not h:
            continue
        rows.append({
            "name": l.commenter.name, "headline": l.commenter.headline or "",
            "company": l.commenter.company or "", "sfdc_contact_id": h.contact_id,
            "flag": h.status.value, "run_date": run_date,
        })
    return validate("contact_observations", rows)


def build_rep_outcomes(leads: list[Lead], run_date: str) -> list[dict]:
    """Adoption outcomes keyed by lead_id (NOT name) -- opportunity_id joined later."""
    rows = [{
        "lead_id": lead_id(l), "rep_action": l.rep_action or "none",
        "opportunity_id": None, "run_date": run_date,
    } for l in leads if l.decision == Decision.surface]
    return validate("rep_outcomes", rows)


def build_displaced_tool_trends(post_results: dict[str, PostClassification], run_date: str) -> list[dict]:
    """DE-IDENTIFIED aggregate over ALL classified posts incl. discards -- monetize the exhaust.
    No names, no URLs, no quotes: just (tool, surface, post_type) -> count."""
    agg = Counter()
    for pc in post_results.values():
        surface = pc.figma_surface.value
        pt = pc.post_type.value
        for tool in pc.tools_mentioned:
            agg[(str(tool).lower(), surface, pt)] += 1
    rows = [{
        "run_date": run_date, "displaced_tool": t, "figma_surface": s,
        "post_type": pt, "post_count": c,
    } for (t, s, pt), c in sorted(agg.items())]
    return validate("displaced_tool_trends", rows)


def build_run_telemetry(metrics: dict, mode: str, run_date: str, warehouse_errors: int) -> list[dict]:
    """One flattened row of run metrics. Signal-quality metadata: intent_events must never be
    consumed in a model without joining this (precision/gate stats say how trustworthy a run was)."""
    adoption = metrics.get("adoption") or {}
    row = {
        "run_date": run_date, "mode": mode,
        "posts_total": int(metrics.get("posts_total", 0)),
        "posts_qualified": int(metrics.get("posts_qualified", 0)),
        "commenters": int(metrics.get("commenters", 0)),
        "surfaced": int(metrics.get("surfaced", 0)),
        "review": int(metrics.get("review", 0)),
        "dropped": int(metrics.get("dropped", 0)),
        "gate_hallucinations_caught": int(metrics.get("gate_hallucinations_caught", 0)),
        "verifier_downgrades": int(metrics.get("verifier_downgrades", 0)),
        "eval_accuracy": metrics.get("eval_accuracy"),
        "surface_precision": metrics.get("surface_precision"),
        "rep_action_rate": adoption.get("rep_action_rate"),
        "warehouse_write_errors": int(warehouse_errors),
        "by_recipe_json": json.dumps(metrics.get("by_recipe", {})),
        "by_lane_json": json.dumps(metrics.get("by_lane", {})),
        "hygiene_json": json.dumps(metrics.get("hygiene", {})),
        "intent_distribution_json": json.dumps(metrics.get("intent_distribution", {})),
    }
    return validate("run_telemetry", [row])
