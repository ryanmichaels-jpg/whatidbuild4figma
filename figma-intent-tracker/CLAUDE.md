# CLAUDE.md -- invariants for the Figma Intent Miner

The agent is small; the trust layer is the product. Do not let this become a
generic scrape-and-spam pipeline. Hold these invariants:

1. **Deterministic ICP filter runs BEFORE any LLM call.** `titles.py` decides who
   reaches the model. Off-ICP commenters must never cost a token. Adding intent
   logic into the LLM step that bypasses the filter is a regression.

2. **No surfaced lead without a verbatim evidence quote.** `gate.py` requires the
   classifier's `evidence_quote` to be an exact substring of the real comment.
   This check runs first and overrides confidence -- a confident but hallucinated
   quote is dropped. Never relax this to a fuzzy/semantic match.

3. **Missing title routes to review, never a silent drop.** Only an explicit
   exclude rule or a present-but-non-buyer title is a drop.

4. **Schema-constrained classifier.** The LLM call uses `output_config` json_schema
   built from the pydantic model. Every field is required so the model cannot omit
   one. Keep prompts bounded and `max_tokens` small.

5. **Cheapest capable model.** `claude-haiku-4-5` for classification. Do not reach
   for a larger model on this narrow task.

6. **Human-in-the-loop only.** Surface a signal + suggested angle to a rep. Never
   auto-DM or otherwise contact a prospect from this code.

7. **No fabrication, provenance always.** Every record carries `source` (demo/live).
   Never invent a person, company, quote, or metric. Business-impact numbers in the
   dashboard stay blank and marked "(confirm with real CRM data)".

8. **Never commit real scraped people's data.** Live output goes to
   `data/*-live.json`, which is gitignored. Committed fixtures are synthetic and
   labeled. The golden set in `data/golden.json` is the eval's ground truth.

9. **Apify is the single scraping provider** (post discovery + comment extraction),
   and both actors are cookie-free (managed server-side auth) -- no LinkedIn session
   cookie. Actor slugs are env vars (`APIFY_POST_SEARCH_ACTOR`, `APIFY_ACTOR`) so the
   source stays configurable and auditable. Extraction drops the post author and
   dedupes to one lead per person (`extract.map_raw_items`) before any LLM call.

10. **Demo mode must stay zero-credential and green.** `MODE=demo python pipeline.py`
    and `pytest` must run with no keys. If you change decision logic, update the
    golden set and keep `accuracy == 1.0` on it (or justify the change).

Pipeline order: DISCOVER -> EXTRACT -> FILTER -> CLASSIFY -> GATE -> NOTIFY -> DASHBOARD.
Files: schema.py (contract), titles.py (filter), classify.py (LLM), gate.py (trust gate),
discover.py / extract.py (Apify), notify.py (Slack), dashboard.py, pipeline.py (orchestrator).
