# CLAUDE.md -- invariants for the Figma Intent Miner

The agent is small; the trust layer is the product. Do not let this become a
generic scrape-and-spam pipeline. Hold these invariants:

0. **Post is the first gate, on TWO axes.** `posttype.py` classifies each post before
   any comment is mined. A post qualifies only if BOTH hold: (a) structure -- post_type
   in `lead_magnet` / `tool_question` / `tool_comparison` (commenting reveals tooling
   intent); AND (b) Figma overlap -- `figma_surface != none`, i.e. the use case the
   poster is offering is something Figma could DISPLACE, mapped against
   `data/figma_capabilities.json` (the Config-2026 surface map: design/make/sites/
   slides/figjam/dev_mode/draw/buzz/motion). "Build a website" -> sites; "make a deck"
   -> slides; "interior room redesign" / CAD / pure engineering -> none -> dropped.
   Keep the capability map current with Figma's actual product surface. The comment
   classifier is conditioned on the post type.

1. **Deterministic ICP filter runs BEFORE any LLM call.** `titles.py` decides who
   reaches the model. Off-ICP commenters must never cost a token. Adding intent
   logic into the LLM step that bypasses the filter is a regression. Personas:
   champion / economic_buyer / user / gatekeeper auto-surface when the gate passes;
   `builder` (founders/PMs/indie/no-code) is a looser prospect tier that ALWAYS
   routes to human review, never auto-surface.

1a. **Verification backs the gate.** `verify.py` runs after the gate and downgrades a
   surfaced lead whose evidence quote reads as praise with no tooling signal. The gate
   proves the quote is REAL (verbatim); verify guards that the quote JUSTIFIES the
   label. Keep it deterministic so it runs zero-cred.

1b. **The richness lever moves leads by evidence substance, POST-TYPE-AWARE**
   (`pipeline.richness_lever`, after verify). A THIN one-word surface lead is held for
   review; a RICH review lead is PROMOTED to surface -- but only if it has surface-eligible
   intent + confidence + (already) a verbatim quote. This is the one case a `builder` can
   auto-surface: a substantive evaluating/active-need comment earns the slot. Bounded on
   purpose -- richness never overrides the verbatim gate or the ICP filter.
   **Lead-magnet exception:** on a `lead_magnet` post the intent lives in the ACT of raising
   a hand for the post's resource, not in the words -- so a THIN one-word comment from an
   ICP-matched buyer/user (persona matched, NOT the looser `builder` tier) STAYS surfaced,
   tagged `quality_flag="thin_handraise"` for a light AE qualification touch. This applies
   ONLY to lead_magnet posts (on tool_question / tool_comparison posts the commenter must
   reveal intent in words, so thin still -> review). The verbatim gate and ICP filter still
   hold: the surfaced quote is the person's real comment, and only a matched buyer/user
   qualifies. The `thin_handraise` flag is excluded from the verifier-downgrade counters.
   For a hand-raise the rep angle is DERIVED from evidence, not free-written by the LLM
   (`pipeline.handraise_angle`): they asked for the post's resource, so they need what it
   does, and the post's `figma_surface` names the Figma product that does it ("they need
   help building a website -> Figma Sites"). Grounded beats generated -- keep it deterministic.

2. **No surfaced lead without a verbatim evidence quote.** `gate.py` requires the
   classifier's `evidence_quote` to be an exact substring of the real comment.
   This check runs first and overrides confidence -- a confident but hallucinated
   quote is dropped. Never relax this to a fuzzy/semantic match.

3. **Missing title routes to review, never a silent drop.** Only an explicit
   exclude rule or a present-but-non-buyer, NON-design-adjacent title is a drop.
   **Design-adjacent safety net:** an off_icp headline that carries a design/UX signal
   (`titles.is_design_adjacent`) but missed every exact persona keyword routes to REVIEW,
   not drop -- so an oddly-titled real designer (e.g. an "Interaction Designer") is never
   silently lost. It still does NOT auto-surface (no persona match, no LLM call) -- a human
   qualifies it. Keeps the "constrain before the LLM" precision story intact.

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

7a. **CRM data is never fabricated.** The Salesforce account match (`accounts.py`)
   uses a clearly-labeled SYNTHETIC fixture (`data/sfdc_accounts.json`) in demo mode;
   the real Salesforce API is the live integration point and account `source` is
   labeled ("demo" / "demo-fallback" / "live"). Never present synthetic accounts as
   real customers. Account match + routing run only for actionable (surface/review)
   leads -- never a CRM lookup on dropped noise.

7b. **CRM hygiene is a PARALLEL output, never a gate.** `hygiene.py` diffs the scraped
   profile (current title/company) against the synthetic SFDC contact fixture
   (`sfdc_contacts.json`) and attaches a `HygieneFlag` (job_change / title_stale /
   no_record / current). It runs on every lead, deterministically, at zero tokens. It
   MUST NOT affect `decision`, scoring, or `routing` -- a lead with a stale record still
   flows through normally; its Slack card just gains one advisory line. Flags go to a
   review queue (`data/hygiene_queue.jsonl`, gitignored) and ONE compact Slack digest per
   run -- never an auto-overwrite of Salesforce. A human confirms before any CRM write.

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

11. **Signals are pluggable config (recipes), and config CANNOT bypass the gates.**
    Discovery signals live in `recipes/*.json`, loaded/validated by `recipes.py` at startup
    (fail-loud, names the file). Discovery + Google-spec + tool-matching iterate ENABLED
    recipes only. A recipe may declare discovery (`surfaces`/`features`, `tool_keywords`,
    `queries`) and routing (`routing_overrides`) -- nothing else: it is validated with
    `additionalProperties:false`, and the engine only sees the NORMALIZED form
    (`name/enabled/figma_surfaces/routing_overrides/signals`), so doc sections never reach
    engine code. The trust gates (0/1/1a/1b/2) are inherited by every recipe and can never be
    altered by config. Never add a code path that lets a recipe touch a gate. Metrics segment
    by recipe so a bad recipe is visible and revertable. See docs/ADDING_A_SIGNAL.md.

Pipeline order: DISCOVER -> EXTRACT -> FILTER -> CLASSIFY -> GATE -> NOTIFY -> DASHBOARD.
Files: schema.py (contract), titles.py (filter), classify.py (LLM), gate.py (trust gate),
discover.py / extract.py (Apify), notify.py (Slack), dashboard.py, pipeline.py (orchestrator).
