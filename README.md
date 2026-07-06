# What I'd Build for Figma

A working demonstration, not a slide deck: a **LinkedIn intent-mining pipeline**
that finds people doing — the hard way, in a competitor tool — something Figma
now does natively, and turns them into a verified, ICP-filtered, account-routed
lead queue for a rep.

**→ The project, with full docs and decision log: [`figma-intent-tracker/`](figma-intent-tracker/)**

## The one-line thesis

The agent is small; the **trust layer is the product**. Anyone can call an LLM to
draft outreach. The hard part is making an LLM workflow trustworthy in production —
constraining its inputs and outputs, wrapping it in quality checks and monitoring,
and routing the result to the right person. That harness is ~90% of this repo; the
LLM is one bounded step inside it.

## What's here

- **Pipeline** — discover posts → gate on post type & Figma displaceability →
  extract commenters → deterministic ICP filter (before any LLM) → schema-locked
  Claude classification → verbatim-evidence gate → Salesforce-aware expansion
  routing → Slack delivery → dashboard.
- **Trust layer** — no lead surfaces without a verbatim quote from their real
  comment; praise-vs-intent verification; self-consistency voting; golden-set eval.
- **Operations** — daily scheduled GitHub Actions run, per-run monitoring log,
  CRM-hygiene byproduct, warehouse sink + dbt models, pluggable signal recipes,
  governance doc with rollout plan and kill-switch.

## Try it (zero credentials)

```bash
cd figma-intent-tracker
pip install -r requirements.txt
MODE=demo python pipeline.py   # full run on labeled synthetic fixtures
python -m pytest -q            # 90 tests
```

Live mode needs `APIFY_TOKEN` and `ANTHROPIC_API_KEY` — see
[`figma-intent-tracker/README.md`](figma-intent-tracker/README.md) for the full
walkthrough: the problem framing, every design decision and tradeoff, what a live
run actually found, and the honest limitations.
