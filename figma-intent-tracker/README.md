# Figma LinkedIn Intent Miner

Find LinkedIn "hand-raiser" / lead-magnet posts where the commenters are
in-market for a design tool -- people trying to do what Figma does (often reaching
for AI tools like Claude), or asking "comment and I'll DM the guide". Pull the
commenters and turn them into a verified, ICP-filtered lead queue for a rep, with
a suggested angle and a verbatim evidence quote for each surfaced lead.

The target is design-tool demand, not Figma-churn specifically: a post does not
need to mention Figma. Discovery looks for the demand signal; the ICP title filter
and the gate decide who is actually worth a rep's time.

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
DISCOVER  Apify native LinkedIn post-search -> candidate posts
POST-TYPE classify each post FIRST; only mine lead_magnet / tool_question /
          tool_comparison (where commenters reveal tooling). Drop showcases +
          off_topic posts before spending any comment-scraping budget.
EXTRACT   Apify post-comments actor (per qualifying post) -> commenters: name, headline, company, comment
FILTER    deterministic ICP title filter -- runs BEFORE the LLM; off-ICP dropped for free
CLASSIFY  claude-haiku-4-5, schema-constrained, CONDITIONED ON POST TYPE
          -> intent + need + verbatim quote + confidence + angle
GATE      no surfaced lead without a verbatim evidence quote; ICP + intent + confidence thresholds
VERIFY    deterministic quality check: downgrade a surfaced lead whose evidence
          quote reads as praise, not tooling intent (catches LLM mislabels)
ACCOUNT   match the commenter's company against Salesforce -> expansion-first routing:
          existing customer + intent = churn/expansion alert to the Account Owner (AE);
          no account = net-new lead for an SDR. Priority (P0..P3) by account tier + intent.
NOTIFY    Slack incoming webhook per surfaced lead (human-in-the-loop; never auto-DMs)
DASHBOARD static HTML: post-type gate, funnel, quality checks, persona/intent,
          account routing, precision vs golden, impact (blank)
```

The post type is the prior. The same comment means different things on different
posts -- "interested" is a hand-raise on a lead-magnet post and noise on a launch-
hype post -- so the post is classified first, off-topic/tooling-irrelevant posts
are dropped before they cost anything, and the comment classifier is told the post
type so it reads short comments in context.

The trust layer, concretely:

- **Constrain inputs (post type first).** `posttype.py` classifies each post before
  any comment is mined. Only `lead_magnet` / `tool_question` / `tool_comparison`
  posts qualify -- showcases and off-topic posts are dropped, so a real designer who
  happens to comment on an HR or finance post never enters the funnel. A
  deterministic "comment-for-asset" detector catches lead magnets for free.
- **Constrain outputs.** A deterministic ICP title filter (`titles.py`) runs
  before any LLM call -- only ICP personas reach the model (design buyers/users,
  plus a looser `builder` prospect tier for founders/PMs/indie/no-code builders),
  so off-ICP commenters cost zero tokens. Builders never auto-surface: the gate
  routes them to human review. The classifier is schema-constrained
  (`output_config` json_schema) so it cannot omit a required field.
- **Trust contract.** No lead is surfaced without a verbatim evidence quote.
  `gate.py` checks the quote is an exact substring of the real comment and drops
  the lead otherwise -- even at high confidence. (The committed golden set
  includes a confident-but-hallucinated classification that the gate catches.)
- **Lightest safe solution.** Free code filter first, then the cheapest capable
  model (`claude-haiku-4-5`) on the narrow set that passed the filter.
- **Quality checks.** Three layers: the verbatim gate; a deterministic
  verification pass (`verify.py`) that downgrades a surfaced lead whose evidence
  quote reads as praise rather than tooling intent (the one mislabel the gate
  can't catch); and a golden-set eval (`tests/`) asserting expected
  surfaced/review/dropped across post types and intents.
- **Monitoring.** `monitoring.py` computes per-run metrics -- post-type and lead
  funnels, intent distribution, hallucinated quotes caught, verification
  downgrades, precision vs golden -- and appends them to a run log so accuracy
  drift is visible over time. `dashboard.py` renders them. Business-impact metrics
  are left blank and marked "(confirm with real CRM data)" -- never fabricated.
- **Expansion-first routing (the PLG motion).** Each actionable lead's company is
  matched against Salesforce (`accounts.py`). An existing paid customer showing
  design-tool intent becomes a churn/expansion alert routed to the Account Owner
  (AE) -- engage the buyer, not the commenter; a company with no account becomes a
  net-new SDR lead. Priority P0..P3 by account tier + intent. The CRM is a
  synthetic, clearly-labeled fixture in demo mode; the Salesforce API is the
  documented live integration point. Real customer data is never fabricated.
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

Live mode needs `APIFY_TOKEN` (discovery + comment extraction) and
`ANTHROPIC_API_KEY` (classifier). Both Apify actors are cookie-free -- discovery
via a native LinkedIn post-search actor (which returns each post's body text and
comment count, so bait posts are ranked by their actual call-to-action plus
comment volume), and comment extraction via a managed-auth comments actor -- so no
LinkedIn session cookie is required. `SLACK_WEBHOOK_URL` is optional (without it, surfaced leads
print their payload). Actor slugs are env vars (`APIFY_POST_SEARCH_ACTOR`,
`APIFY_ACTOR`). Extraction drops the post author and dedupes to one lead per
person before classifying.

This pipeline has been run end-to-end on real LinkedIn posts: discovery returned
real Figma-switching posts, extraction pulled real commenters cookie-free, the
ICP filter correctly rejected off-ICP commenters (e.g. EV-charging engineers on a
design thread), and the verbatim gate caught real LLM hallucinations (confident
classifications whose evidence quote was not an exact substring). Committed data
stays synthetic; real runs write to gitignored `data/*-live.json`.

## JD mapping

| JD theme | Where it lives |
| --- | --- |
| Constrain LLM outputs | `titles.py` (pre-LLM filter) + json_schema classifier in `classify.py` |
| Quality checks | `gate.py` verbatim gate + `tests/` golden-set eval |
| Monitoring | `dashboard.py` funnel + persona/intent + precision vs golden |
| Track adoption/impact | dashboard impact panel (blank pending real CRM data) |
| Named stack (Anthropic, Slack, Salesforce, SQL-shaped data) | haiku classifier, Slack notify, Salesforce account match (`accounts.py`), structured pydantic records |
| PLG -> enterprise expansion signal | design-tool intent matched to Salesforce accounts -> churn/expansion alert to the AE vs net-new to an SDR |

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
Apify (LinkedIn post discovery + comment extraction, single provider), Salesforce
account match for expansion routing (synthetic fixture in demo; API integration
point for live), Slack incoming webhooks, static HTML dashboard. No framework; the
orchestration is plain code so every step is inspectable.
