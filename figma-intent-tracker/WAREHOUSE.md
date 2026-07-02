# Warehouse layer — Slack gets the lead, Snowflake gets the memory

The pipeline is a **sensor**; Snowflake is **institutional memory**. Slack delivery is
ephemeral — a rep sees a card and acts. Everything the run *learns* is also written to the
warehouse as queryable, partitioned tables, so RevOps, data science, and PMM can join it. That
join is what turns a scraper into a **GTM data asset**.

Writes are **best-effort**: a sink failure never blocks Slack or fails the run (it's counted as
`warehouse_write_errors` and logged). Backend is pluggable (`WAREHOUSE_BACKEND`): `local`
(parquet, JSONL fallback, under `data/warehouse/<table>/dt=<run_date>/`) or `snowflake`
(stage the partition → `COPY INTO`; lazy import, no-ops without the connector).

## Tables

| Table | Grain | Notes |
|---|---|---|
| `external_intent_events` | one surfaced lead | **Gate-inherited**: only `decision==surface` leads with a verbatim-verified quote — a hallucinated lead is unrepresentable. Identified (person/company/quote). |
| `contact_observations` | one lead | CRM-hygiene diff for **all** leads incl. non-ICP (a job change is valuable regardless of ICP). |
| `rep_outcomes` | one surfaced lead | Adoption, keyed by `lead_id` (**not name**); `opportunity_id` joined later. |
| `run_telemetry` | one run | Flattened metrics (funnel, gate stats, precision, adoption, warehouse errors). **Signal-quality metadata — never consume `external_intent_events` in a model without joining this** (it says how trustworthy the run was). |
| `displaced_tool_trends` | tool × surface × post_type | **De-identified aggregate** over ALL classified posts incl. discards — we monetize the exhaust. No names, URLs, or quotes. |

`lead_id` = `sha1(profile_url | post_url)[:12]`, shared across tables for joins.

## Retention

Slack is ephemeral; the warehouse is the system of record. Raw scraped comment text has a
**30-day** retention window (see `GOVERNANCE.md`); the warehouse tables persist the *derived*
records (events, observations, outcomes, de-identified trends) as institutional memory.

## The queries this layer exists for (copy-paste)

**(a) Influenced pipeline + win rate — an intent event preceded first touch by < 30 days, by surface**
```sql
select
    e.figma_surface,
    count(distinct o.opportunity_id)                                        as influenced_opps,
    sum(o.amount)                                                           as influenced_pipeline,
    round(avg(case when o.stage_name = 'Closed Won' then 1.0 else 0.0 end), 3) as win_rate
from external_intent_events e
join salesforce.opportunities o
      on lower(e.company) = lower(o.account_name)
     and o.created_date between e.run_date::date and dateadd('day', 30, e.run_date::date)
group by e.figma_surface
order by influenced_pipeline desc nulls last;
```

**(b) Champion departures — a paid account just lost a champion; the new company is a warm door**
```sql
select name, old_account, new_company, plan, old_account_signal, new_company_signal, run_date
from champion_departure
order by run_date desc;
```

**(c) Recipe volume + run precision over time**
```sql
-- overall precision trend + per-recipe volume. Per-recipe PRECISION needs per-recipe golden
-- labels (the config-2026 surfaces don't have them yet -- grown via the 👎 feedback loop).
select run_date, eval_accuracy, surface_precision, by_recipe_json
from run_telemetry
order by run_date;
```
