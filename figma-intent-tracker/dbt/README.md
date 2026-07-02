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

## Sources

`external_intent_events` / `contact_observations` / `rep_outcomes` come from this pipeline's
warehouse writes. `salesforce.contacts` / `salesforce.accounts` are the standard Salesforce syncs
(Fivetran/native). Wire them in `sources.yml` when deploying.

## Read-back contract

The only coupling from warehouse → pipeline is a single JSON snapshot
(`account_heat_snapshot.json`, `{ "<company>": <heat_float> }`). It is optional by design:
present → heat sharpens timing; absent → identical behavior. Nothing in the warehouse can change
a routing *decision* — only nudge priority within a bounded rule.
