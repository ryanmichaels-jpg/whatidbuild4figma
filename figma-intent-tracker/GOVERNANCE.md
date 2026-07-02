# Governance & Rollout — Figma Intent Miner

One page. How this ships, who owns what, where the guardrails are, and how it's turned off.
The point of the whole system is trust; governance is where trust becomes operational.

## Rollout — earn the right to scale, pod by pod

1. **Pilot (weeks 1–2):** one AE pod, **5 reps**, live in one Slack channel. Leads delivered
   daily; reps react (👍 booked / 👎 bad lead / 🔁 wrong route).
2. **Success gate (measured, not vibes):** advance only if
   - **rep action rate ≥ 50%** (acted / surfaced), and
   - **precision ≥ 85%** vs the golden set (which the pilot's 👎 labels have grown).
3. **Expand pod-by-pod:** on passing the gate, add one pod at a time, re-checking both
   numbers per pod. A pod that regresses below gate pauses new leads until retuned. No
   org-wide launch before three consecutive pods clear the gate.

## Owners — distributed, not a central dependency

| Area | Owner | Responsibility |
|---|---|---|
| Routing rules (`accounts.py`, intercept tiers) | **SalesOps** | Owns who-gets-what and priority tiers; approves changes. |
| Rep training + feedback norms | **Enablement** | Trains reps to react; keeps the 👍/👎/🔁 signal honest. |
| Secrets, infra, cron | **GTM Systems** | Owns `APIFY_TOKEN` / `ANTHROPIC_API_KEY` / `SLACK_WEBHOOK_URL`, the GitHub Action, uptime. |
| The engine (gates, classifier, recipes) | **Me (AI Sales Engineer)** | Owns the trust chain and the code; reviews recipe PRs for gate-bypass. |

Distributed ownership is the design goal (JD: "distributed adoption rather than central
dependency"). No single person is a bottleneck; the config-vs-code split (below) is what
makes that safe.

## Data & privacy

- **Public LinkedIn data only.** Post bodies and public comments; no private/connection-gated data.
- **No auto-DMs, ever.** The system surfaces a signal + suggested angle to a rep. A human
  decides and acts. This is enforced in code (there is no outbound-message path to a prospect).
- **PII stays out of run metrics.** `run_log.jsonl` carries counts and rates only; per-person
  data (raw comments, hygiene flags, feedback) lives in gitignored files.
- **Retention window: 30 days.** Raw scraped comment text (`comments-live.json`, hygiene
  queue) is purged after 30 days; only non-PII aggregates in the run log persist beyond that.
- **System of record vs ephemeral.** Slack delivery is ephemeral; the **warehouse is the system
  of record** for what the pipeline learned. Warehouse tables persist the *derived* records
  (intent events, observations, outcomes, de-identified trends); raw comment text still obeys the
  30-day window above and is not warehoused.

## Source risk & kill-switch

- **LinkedIn ToS exposure.** Scraping LinkedIn crosses its ToS. We reduce exposure by using
  **cookie-free, managed-auth third-party APIs** (harvestapi / Apify) — we never handle a
  user's LinkedIn session cookie, so no individual account is put at risk.
- **Kill-switch.** Revoke `APIFY_TOKEN`. With no token the pipeline **no-ops cleanly**
  (exit 0) — discovery and extraction simply return nothing. There is no state to unwind
  and nothing keeps running.
- **Legal check-in.** Before org-wide expansion, Legal signs off on the scraping posture and
  the retention window. Pilot scope is small and reversible by design to make that review cheap.

## Change management — signals are config, not deploys

New intent signals ship as **recipe JSON** (`recipes/*.json`), not code. A recipe declares
what to search and how to route within it, and is a **PR reviewed by SalesOps** — not an
engineering deploy. Critically, **a recipe cannot alter the trust gates** (ICP filter,
verbatim gate, verify, richness): those are inherited automatically and enforced in code, so
a bad or aggressive recipe can waste some Apify spend but can **never** lower the quality bar
or surface an unverified lead. That property is the whole reason a GTM team can ship its own
signal without an engineer in the loop. See `docs/ADDING_A_SIGNAL.md`.
