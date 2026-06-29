# Figma LinkedIn Intent Miner

Find LinkedIn "hand-raiser" posts about leaving Figma ("we're replacing Figma",
"comment and I'll DM my migration guide", "what should we switch to?"), pull the
commenters, and turn them into a verified, ICP-filtered lead queue for a rep --
with a suggested angle and a verbatim evidence quote for each surfaced lead.

## Problem

Calling an LLM to draft outreach is the easy part. The hard part -- and the
actual JD pain for Figma's Sales AI Engineer role -- is making an LLM workflow
**trustworthy in production**: constraining outputs, building quality checks and
monitoring, and tracking adoption. A naive version of this tool is a
scrape-and-spam pipeline that surfaces hallucinated signals and burns rep trust.

## What I built

A small, code-orchestrated pipeline where **the LLM is one bounded step** and the
trust layer around it is the product.

```
DISCOVER  Apify LinkedIn post-search actor -> intent post URLs
EXTRACT   Apify post-comments actor -> commenters: name, headline, profileUrl, comment
FILTER    deterministic ICP title filter -- runs BEFORE the LLM; off-ICP dropped for free
CLASSIFY  claude-haiku-4-5, schema-constrained -> intent + need + verbatim quote + confidence + angle
GATE      no surfaced lead without a verbatim evidence quote; ICP + intent + confidence thresholds
NOTIFY    Slack incoming webhook per surfaced lead (human-in-the-loop; never auto-DMs)
DASHBOARD static HTML: funnel, persona/intent breakdown, precision vs golden, impact (blank)
```

The trust layer, concretely:

- **Constrain outputs.** A deterministic ICP title filter (`titles.py`) runs
  before any LLM call -- only buyer/user personas reach the model, so off-ICP
  commenters cost zero tokens. The classifier is schema-constrained
  (`output_config` json_schema) so it cannot omit a required field.
- **Trust contract.** No lead is surfaced without a verbatim evidence quote.
  `gate.py` checks the quote is an exact substring of the real comment and drops
  the lead otherwise -- even at high confidence. (The committed golden set
  includes a confident-but-hallucinated classification that the gate catches.)
- **Lightest safe solution.** Free code filter first, then the cheapest capable
  model (`claude-haiku-4-5`) on the narrow set that passed the filter.
- **Quality checks.** The gate + a golden-set eval (`tests/`, asserting expected
  surfaced/review/dropped) + Slack delivery.
- **Monitoring.** `dashboard.py` renders the funnel, persona/intent breakdown,
  and precision vs golden. Business-impact metrics are left blank and marked
  "(confirm with real CRM data)" -- never fabricated.
- **Human-in-the-loop.** Surfaces a signal + suggested angle to a rep; never
  auto-DMs a prospect.

## How to run

Demo mode is zero-credential and uses committed synthetic, labeled fixtures.

```bash
pip install -r requirements.txt
MODE=demo python pipeline.py     # runs the full pipeline, prints funnel + eval, renders dashboard.html
python -m pytest -q               # golden-set eval + unit tests
```

Live mode runs against real LinkedIn posts. Copy `.env.example` to `.env`, fill
in keys, then:

```bash
export $(grep -v '^#' .env | xargs)
MODE=live python pipeline.py
```

Live mode needs `APIFY_TOKEN` (both discovery and comment extraction) and
`ANTHROPIC_API_KEY` (classifier); `SLACK_WEBHOOK_URL` is optional (without it,
surfaced leads print their payload). Actor slugs are env vars
(`APIFY_POST_SEARCH_ACTOR`, `APIFY_ACTOR`).

## JD mapping

| JD theme | Where it lives |
| --- | --- |
| Constrain LLM outputs | `titles.py` (pre-LLM filter) + json_schema classifier in `classify.py` |
| Quality checks | `gate.py` verbatim gate + `tests/` golden-set eval |
| Monitoring | `dashboard.py` funnel + persona/intent + precision vs golden |
| Track adoption/impact | dashboard impact panel (blank pending real CRM data) |
| Named stack (Anthropic, Slack, SQL-shaped data) | haiku classifier, Slack notify, structured pydantic records |
| PLG -> enterprise expansion signal | switching-intent on Figma posts, scored against the buyer committee |

## Compliance posture (a feature, not an afterthought)

LinkedIn scraping crosses LinkedIn's ToS and touches personal data
(GDPR/CCPA). The decision here is to **proceed deliberately**, with guardrails:

- The scraping source is **configurable** (Apify actor IDs are env vars), so the
  pipeline is not welded to one method.
- **Human-in-the-loop**: the tool surfaces signals to a rep and never auto-DMs.
- **No real people's data is committed**: live output is written to
  `data/*-live.json`, which is gitignored. The committed repo is synthetic.
- Every record carries **provenance** (`source: demo|live`); nothing is invented.

This is meant to read as judgment, not recklessness -- and the same trust layer
(verbatim-evidence gate + ICP constraint) is what keeps the pipeline from
becoming generic scrape-and-spam.

## Stack

Python, pydantic (the trust contract), Anthropic `claude-haiku-4-5` (classifier),
Apify (LinkedIn post discovery + comment extraction, single provider), Slack
incoming webhooks, static HTML dashboard. No framework; the orchestration is
plain code so every step is inspectable.
