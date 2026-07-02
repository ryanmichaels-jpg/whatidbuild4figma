# dbt models — derived intelligence in the warehouse

These models are **not run by the Python pipeline.** They run in the warehouse on warehouse
cadence (dbt Cloud / a scheduled `dbt run`), reading the tables the pipeline writes
(`external_intent_events`, `contact_observations`, `rep_outcomes`). The pipeline only ever
**reads their output back** — it never computes them. That separation is the point: the sensor
(pipeline) stays simple; the institutional memory (warehouse) is where cross-run intelligence
accrues, owned by RevOps/data.

## Models

- **`account_heat.sql`** — a decay-weighted external-intent score per company, weighted by role
  diversity (distinct Figma surfaces seen) and seniority (from the contact's title). Weights are
  dbt vars in `dbt_project.yml` so RevOps tunes them without a code change. A snapshot of this
  table is exported to `data/warehouse/account_heat_snapshot.json`; `accounts.py` reads it back
  into the intercept score (bounded: heat can escalate priority by at most one tier). If the
  snapshot is absent, the pipeline behaves exactly as before — the read-back is the dashed arrow.
- **`champion_departure.sql`** — contacts flagged `job_change` whose old Salesforce account is a
  paid customer. Emits both sides of the event: the old account as a **churn_risk** (a champion
  just left) and the new company as a **warm_door** (a known advocate just landed there).

## Sources & running it

Sources are declared in `models/sources.yml` (that's the "wiring"):

- **`pipeline`** — the five tables the sink lands (`external_intent_events`, `contact_observations`,
  `rep_outcomes`, `run_telemetry`, `displaced_tool_trends`). Because they're *landed* (via
  `COPY INTO`), the models read them with `source()`, not `ref()`. Includes a freshness check
  (a stale pipeline is a monitoring signal) and column tests (lead_id not-null, confidence in
  [0,1], hygiene flag accepted-values).
- **`salesforce`** — `contacts` / `accounts` / `opportunities` synced by Fivetran/native.

Database/schema names come from env vars (`PIPELINE_DB`, `PIPELINE_SCHEMA`, `FIVETRAN_DB`,
`SALESFORCE_SCHEMA`) so nothing warehouse-specific is hardcoded.

**To run against a real warehouse:**
```bash
cp dbt/profiles.example.yml ~/.dbt/profiles.yml     # then fill in / export the env vars
export PIPELINE_DB=ANALYTICS PIPELINE_SCHEMA=PIPELINE SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=...
cd dbt
dbt deps                 # installs dbt_utils (see packages.yml)
dbt source freshness     # is the pipeline landing data on schedule?
dbt build                # runs models + source/column tests
```
Export the `account_heat` snapshot the pipeline reads back:
```bash
dbt run-operation export_account_heat   # or a scheduled UNLOAD -> data/warehouse/account_heat_snapshot.json
```

## Read-back contract

The only coupling from warehouse → pipeline is a single JSON snapshot
(`account_heat_snapshot.json`, `{ "<company>": <heat_float> }`). It is optional by design:
present → heat sharpens timing; absent → identical behavior. Nothing in the warehouse can change
a routing *decision* — only nudge priority within a bounded rule.
