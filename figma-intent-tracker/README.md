# Figma LinkedIn Intent Miner

Find LinkedIn posts where someone is doing — the hard way, in a competitor tool —
something **Figma now does natively**, pull the people raising their hand in the
comments, and turn them into a **verified, ICP-filtered, account-routed lead queue**
for a rep. Each surfaced lead carries a verbatim evidence quote, a suggested angle,
and a Salesforce-aware routing decision.

> **Thesis:** the agent is small; the **trust layer is the product.** Anyone can
> call an LLM to draft outreach. The hard part — and the actual job — is making an
> LLM workflow *trustworthy in production*: constraining its inputs and outputs,
> wrapping it in quality checks and monitoring, and routing the result to the right
> person. That harness is ~90% of this repo. The LLM is one bounded step inside it.

---

## 1. The problem (and why it maps to the role)

A naive version of this tool is a scrape-and-spam pipeline: search LinkedIn, pull
commenters, have GPT write them a DM. It would surface hallucinated signals, waste
reps' time on non-buyers, and burn trust on day one.

The interesting problem is the opposite of "call the LLM." It's everything *around*
the call:

- **Constrain outputs** — make the model physically unable to return garbage, and
  spend tokens only on inputs that already passed cheap deterministic filters.
- **Quality checks + monitoring** — prove the workflow is accurate, catch its
  failure modes, and make drift visible.
- **Track adoption / impact** — connect the output to the CRM so it produces a
  *sales action* (expansion vs. new-logo), not just a list.
- **Product-led → enterprise expansion** — Figma grows bottom-up then expands into
  accounts; reps run on **expansion signals**. This tool manufactures those signals
  from public intent and routes them against Salesforce.

Named tools in the work: **Anthropic** (the classifier), **Salesforce** (account
match + routing), **Slack** (delivery), and structured, SQL-shaped records
(pydantic) throughout.

---

## 2. What it does — the pipeline

```
DISCOVER   native LinkedIn post-search  ⋃  Google boolean search   (two retrievers)
           → enrich Google hits (full body + comment count)
           → smart filter: AND names a displaced tool · NOT off-domain stop-list
           → cap to top N
POST GATE  classify each post on TWO axes, before mining a single comment:
           (a) structure  — is commenting a tooling tell? (lead_magnet / tool_question / tool_comparison)
           (b) Figma overlap — could Figma DISPLACE this use case? (figma_surface ≠ none)
EXTRACT    cookie-free comments actor, per post, author dropped + deduped
FILTER     deterministic ICP title filter — buyer / user / builder tiers — BEFORE any LLM
CLASSIFY   claude-haiku-4-5, schema-constrained, conditioned on the post type,
           with self-consistency voting on borderline calls
GATE       no surfaced lead without a VERBATIM evidence quote (exact substring)
VERIFY     downgrade a surfaced lead whose quote reads as praise, not intent
RICHNESS   grade how much the comment actually says (thin hand-raise → rich)
ACCOUNT    match company → Salesforce → expansion-first routing (territory AE, P0–P3)
NOTIFY     Slack per surfaced lead (human-in-the-loop — never auto-DMs a prospect)
MONITOR    funnel + per-run metrics + append-only run log + static HTML dashboard
```

Each stage exists because a live run proved it was needed. The sections below are the
decision log — what we chose, what we traded away, and why.

---

## 3. The trust layer (the actual product)

| Guarantee | Where | What it buys |
|---|---|---|
| **Constrain inputs** | `posttype.py` | Off-topic / non-displaceable posts dropped before they cost a token or a scrape |
| **Constrain ICP** | `titles.py` | Deterministic title filter runs *before* the LLM; off-ICP people cost nothing |
| **Constrain outputs** | `classify.py` json_schema | The model cannot omit a field or return an off-menu label |
| **Trust contract** | `gate.py` | No lead surfaces without a verbatim evidence quote — catches hallucinations the model is confident about |
| **Verification** | `verify.py` | Catches the one mislabel the gate can't: praise scored as intent |
| **Self-consistency** | `classify.py` | Re-samples borderline one-word comments and votes, so they land consistently |
| **Signal richness** | `richness.py` | Grades *how much* the evidence says, so reps see substantive comments first |
| **No fabrication** | everywhere | Synthetic CRM is labeled; provenance on every record; real data gitignored |
| **Monitoring** | `monitoring.py` + `dashboard.py` | Funnel, hallucinations caught, verifier downgrades, precision vs golden, run log |

The recurring principle: **the LLM proposes bounded fields; deterministic code
disposes.** The model never decides "surface this" or "route to an AE" — it returns
an intent label, a confidence, and a quote, and plain, auditable `if`-statements make
every consequential decision. A hallucinated quote can't escape a substring check no
matter how confident the model is.

---

## 4. Key decisions & tradeoffs (the brain dump)

### 4.1 Discovery — recall vs. precision, and a dumb search engine

**Decision: two retrievers unioned, precision enforced in code, not in the query.**

The journey:

- **Firecrawl → Apify.** Started intending Firecrawl `/search`, but LinkedIn's public
  indexing is thin. Moved to Apify actors for LinkedIn-native discovery.
- **The cookie problem.** The first comments actor required a LinkedIn `li_at`
  session cookie (it logged *"LinkedIn requires authentication… provide your li_at
  cookie"* and returned 0). **Tradeoff:** a cookie means handling someone's
  authenticated session — a compliance and security liability. **Decision:** switch
  to **cookie-free, managed-auth actors** (`harvestapi`) for both discovery and
  comments. Verified live: real commenters with name + headline + company, no cookie.
- **Native search is fuzzy and ignores boolean.** Empirically tested: a boolean query
  `("After Effects" OR Principle) AND ("comment")` returned **0** posts; even quotes
  weren't honored (`"After Effects"` returned a Claude-ads post). The actor does
  relevance matching, not keyword logic. **Decision:** stop fighting it — give it
  short natural-language queries for **recall**, and move **precision into our own
  code** (the "smart layer").
- **The smart layer = boolean emulation client-side.** `smart_discover()` runs many
  simple queries (OR), then enforces **AND** (post body must name a Figma-displaced
  tool, whole-word) and **NOT** (a stop-list of off-domain noise: outbound-sales,
  crypto, real estate, follower-count spam). That's the boolean query the actor
  couldn't run — executed where it works. Live: 80 recalled → 39 kept.
- **Second retriever: Google honors boolean.** `discover_google()` runs
  `site:linkedin.com/posts "After Effects" ("comment" OR "I'll send")` via an Apify
  Google actor. **Tradeoff:** Google returns only title + snippet — no body, no
  comment count. **Decision:** union it anyway (additive recall), and **enrich** the
  top Google hits via a post-detail actor to fetch full body + comment count so they
  rank and gate fairly. Live payoff: Google ~10×'d the candidate pool (40 → ~380) and
  **recovered surfaces native search missed entirely** (a 136-comment "Jitter vs
  After Effects" post; ProtoPie vs Figma; Builder.io design-to-code).

**Net tradeoff accepted:** higher recall means more candidates the gate must filter
(~hundreds of cheap haiku calls per run). We pay that because the gate is trusted and
the alternative — a clever query that misses the niche displacement posts — is worse.

### 4.2 The post-type gate — "the post is the prior"

**Decision: classify the post *before* mining its comments, and drop most of them.**

A live run made the case: the same comment means opposite things on different posts.
"Interested!" is a hand-raise on a *lead-magnet* post and noise on a *launch-hype*
post. So we classify the post first and only mine the types where commenting reveals
tooling intent (lead_magnet / tool_question / tool_comparison). Showcases and
off-topic posts are dropped — **no comment-scraping budget spent on them.** The
comment classifier is then *told the post type*, so it reads a one-word comment in
context.

**Tradeoff:** an extra LLM call per post. Worth it — it removes the largest source of
noise (e.g., dropping ~24 of 35 posts in one run) before the expensive stages.

**Decision: on a lead-magnet post, scrape the comments *deep*.** Once a post qualifies,
the value *is* the commenters, so a shallow comment cap silently drops leads. Live proof:
a viral *"build a website with Claude Code"* bait post had ~90 commenters, but a 40-comment
cap only reached 20 of them — surfacing **3** ICP designers. Scraping the full set surfaced
**8** (including two Webflow devs and two design leaders). The cap, not the filter, was the
bottleneck. So `APIFY_COMMENT_LIMIT` defaults to **150** (env-tunable).
**Tradeoff:** more comments = more Apify credits and more classifier calls — but the
deterministic ICP filter runs *before* the LLM, so the bulk of a viral thread (63 of 87
were off-ICP on that post) costs **zero tokens**. Token cost scales with ICP matches, not
raw comment volume.

### 4.3 The displaceability reframe — "could Figma replace this?"

**Decision: qualify a post by Figma-capability overlap, not the word "design."**

The sharpest reframe of the project. "Design" is ambiguous; the real question is
*could Figma displace the solution this poster is offering?* We built a
**capability map** (`figma_capabilities.json`) grounded in **Config 2026** (Figma
Design, Make, Sites, Slides, FigJam, Dev Mode/Code Layers, Draw, Buzz, Motion), and a
**displacement map** (`displacement_map.json`) mapping each surface to the competitor
it eats (After Effects → Motion, Webflow/Framer → Sites, PowerPoint/Gamma → Slides,
Miro → FigJam, Claude Code → Make, Zeplin/Anima → Dev Mode, Midjourney → Buzz).

The gate now outputs `figma_surface`. Live proof of judgment, not keyword matching:
a *"redesign your room with Claude"* (interior decor) post correctly drops
(`figma_surface = none`) while *"build a website with Claude"* qualifies (Sites) and
*"Presentation designer vs Claude"* qualifies (Slides). The discovery queries hunt the
**displaced competitor by name**, so we find people using the exact tools Config 2026
just made redundant.

**Tradeoff:** the capability map is hand-curated from Figma's own writeups and goes
stale after each Config. **Mitigation noted in code:** a capability-sync agent could
extract it from Figma's keynote/recap on a schedule. Left as a documented next step
rather than fabricated.

### 4.4 ICP filter — deterministic, before the LLM, and repeatedly debugged by live data

**Decision: a free, deterministic title filter constrains who reaches the model.**

Buyer-committee tiers from Figma's real expansion motion: **champion**
(design systems, DesignOps, head of design), **economic_buyer** (VP Product/Design,
CPO, eng leaders), **user** (product/UX/UI designers, and — after live data — Webflow
devs, content/visual/graphic/presentation designers), **gatekeeper** (IT/security),
plus a looser **builder** prospect tier (founders/PMs/indie/no-code) that **never
auto-surfaces — it routes to human review.**

This filter was hardened by bugs that *only live data surfaced* — a theme worth
foregrounding as evidence of monitoring discipline:

- `intern` matched "internal"/"international" → made it **whole-word**.
- `student` matched "Student Support" (a service area) → **whole-word + a
  service-phrase exception**.
- `anima` (the handoff tool) matched "**anim**ation" everywhere → **whole-word** tool
  matching.
- `cpo` matched a "**Chief People Officer**" (HR) as a product buyer → never assign
  economic_buyer under HR context. But over-correcting (requiring the fully-spelled
  "chief product officer") then **dropped a real Chief *Product* Officer who abbreviated**
  — *"CPO | Product, Design & Strategy"* with a detailed Figma Make need. Final rule:
  resolve the `cpo` abbreviation to economic_buyer **only in a product/design context and
  never under HR context** — catches the product exec, still rejects the people exec.

**Tradeoff:** a deterministic filter has false negatives (a real buyer with an oddly
phrased title). We mitigate three ways: **missing titles route to review, never a silent
drop**; we **broaden the include lists** when live data shows a miss (e.g. adding
`interaction designer` after one was dropped); and a **design-adjacent safety net** —
an off_icp headline that still carries a design/UX signal (`is_design_adjacent`) routes to
**review** rather than drop, so an oddly-titled real designer is never silently lost. The
safety net deliberately does **not** auto-surface (no persona match, no LLM spent) — a
human qualifies it — so the "constrain before the model" precision story holds while the
false-negative rate drops.

### 4.5 The classifier — cheapest capable model, schema-locked, post-conditioned

**Decisions:** `claude-haiku-4-5` (the narrow task doesn't need a frontier model —
"lightest safe solution"); **schema-constrained** structured output so it can't omit
a field; **conditioned on the post type** so short comments read in context; and
**self-consistency** — borderline calls (surface-eligible but low confidence or a
one/two-word quote) are re-sampled and majority-voted, with confidence scaled by
agreement. This fixed an observed flaw where identical one-word "Website" comments
landed `active_need` on one run and `noise` on the next.

**Tradeoff:** the API rejected `minimum`/`maximum` on the confidence number — we
dropped them from the JSON schema and let pydantic enforce the 0–1 range after
parsing. Self-consistency triples the call count on borderline items only.

### 4.6 The gate, verification, and richness — three quality layers on the evidence

- **Gate (`gate.py`):** verbatim-substring check first. A confident-but-hallucinated
  quote is dropped regardless of confidence. The committed golden set includes such a
  case so the test suite proves the gate catches it; live runs caught real ones every
  time (e.g., 6 in one run).
- **Verify (`verify.py`):** the gate proves the quote is *real*; verify proves it
  *justifies the label* — it downgrades a surfaced lead whose evidence is praise
  ("love this!") with no tooling signal. The one mislabel the gate can't see.
- **Richness (`richness.py`):** grades how much the comment says (thin → rich), so a
  rep sees *"Gamma is still limited — the API can't generate sales-ready proposals"*
  (rich) above *"Interested!"* (thin). The gate requires evidence; richness grades it.

**Tradeoff:** richness is a heuristic (length + names a tool + states a need), not a
model. Deterministic and cheap on purpose.

### 4.7 Account routing — the PLG → enterprise expansion motion

**Decision: a lead isn't a person, it's a routing decision against the CRM.**

`accounts.py` matches the commenter's company to Salesforce and routes
**expansion-first**: an existing paid customer showing design-tool intent is a
**churn/expansion alert to the Account Owner (AE)** (engage the buyer, not the
commenter); a free/pro customer is an **upsell**; a no-match company is a **net-new
lead for the territory AE**. Priority P0–P3 by account tier + intent. This is the
literal expansion motion the JD describes — public intent → CRM context → the right
rep, the right play.

**Routing reflects Figma's actual org — no SDR function.** Figma's CRO has said
publicly that Figma runs no SDR team; AEs own the full motion including net-new and
expansion (source: 20Sales podcast, Mar 2026). So every human-routed lane goes to a
**territory AE**, never an SDR — modeling the real customer, not a generic B2B org.

**Tradeoff / honesty:** matching real people's companies to **Figma's real
Salesforce** requires Figma's CRM, which an applicant can't have. So the CRM is a
**clearly-labeled synthetic fixture** (`sfdc_accounts.json`); `accounts.py` documents
the Salesforce API as the live integration point and labels every record's source.
**Nothing about real customers is fabricated.** On live runs, real companies don't
match the synthetic CRM and correctly route as net-new — which is the honest outcome.

### 4.7b CRM hygiene — one scrape, two workflows

**Decision: the same scrape that finds leads also cleans the CRM — for free.**

Figma's Marketing Ops team went on record (Clay case study) that their core GTM pain was
**stale Salesforce contacts** — years of people who changed jobs or titles. But the miner
already sees every commenter's **current** headline and company. So `hygiene.py` runs after
the ICP filter, **deterministically and at zero tokens**, diffing the scraped profile
against the SFDC contact record and emitting a flag: `job_change` (company moved),
`title_stale` (same company, new title), `no_record` (net-new to the CRM), or `current`.

Two rules make it trustworthy: **(1) it never auto-overwrites Salesforce** — flags go to a
review queue (`data/hygiene_queue.jsonl`) and one compact Slack digest per run ("2 stale
records: 1 job change, 1 title mismatch"), and a human confirms before any write; and
**(2) it never touches lead scoring or routing** — it's a parallel output, not a gate. A
surfaced lead with a stale record flows through normally and just gains one advisory line
on its card. This is the JD's "CRM hygiene" bullet, covered as a byproduct rather than a
second system.

### 4.7c Stack-aware routing — the intent × usage intercept (where this lives at Figma)

**Decision: external intent is only half the join — score it against internal usage.**

Figma decides *when sales intercepts a PLG account* by joining **internal product signals
(Snowflake)** with **external signals (Clay)**. This pipeline is the external half. So after
the base CRM route, an **intercept pass** (`accounts._apply_intercept`, deterministic, no
LLM) joins the intent label with a synthetic `product_signals` block (Pro seats, 90-day seat
growth, feature adoption, recency) and adjusts **timing**:

- **active_need + seats already growing → escalate one priority tier** ("expansion-ready, warm").
- **curious + heavy usage → nurture/insight, not a call task** (don't burn a hot account on a tire-kick).
- **active_need + no product footprint → standard net-new** (unchanged).

Every card gets a **"Why now"** line derived from the join — e.g. *"active_need at an account
with 300 Pro seats, +38% seats/90d, uses design, motion."* That's the difference between "here's
a lead" and "here's why a rep should call *today*."

**Where it lives at Figma / honesty:** in production this join runs in **Clay**, reading
**Snowflake** and firing playbook functions to reps — so this module's real surface is a Clay
table/webhook, not a standalone app. The repo **simulates that interface** (the `product_signals`
block stands in for the Snowflake read) and deliberately builds **no Clay integration** — just
makes the boundary explicit so the code reads like it was designed to slot in.

### 4.7d Adoption feedback loop — reps are the labeling function

**Decision: measuring precision isn't enough — measure whether reps ACT.**

Precision vs. a golden set says the pipeline is *right*; it doesn't say the pipeline is
*used*. So every Slack card carries a reaction footer — **👍 booked · 👎 bad lead · 🔁 wrong
route** — and `feedback.py` collects those reactions (pluggable backend: a `demo` file for
zero-key runs, a documented `slack_api` `reactions.get` flow for live). The dashboard's
**top-line metric is now rep action rate (acted / surfaced)** — above precision — with
per-Figma-surface and per-post-type breakdowns so you can see *which* signals reps act on.

The point is the **loop**: a 👎 is a labeled negative → it's appended to
`data/golden_candidates.jsonl` → reviewed and promoted into `golden.json` → the golden set
grows → precision measurement improves → the gates get retuned. Reps labeling production data
is how the trust layer keeps earning trust. (Per-lead feedback lives in `data/feedback.jsonl`,
gitignored; the run log carries only the aggregates — no PII.)

### 4.8 Monitoring & the demo/live split

- **Monitoring (`monitoring.py`):** every run computes a funnel, intent distribution,
  hallucinations caught, verifier downgrades, precision vs. the golden set, and the
  **adoption** aggregate (rep action rate), and appends them to a run log so accuracy
  and adoption drift are visible over time. The dashboard renders it.
- **Demo/live split:** **demo mode runs zero-credential** on committed synthetic,
  labeled fixtures + recorded LLM outputs. This is what makes the repo reproducible,
  testable (a golden-set eval), and safe to commit (no real people's data). **Live
  mode** (`MODE=live` + keys) runs the real thing. The same code path; only the
  connectors differ.

### 4.9 Recipes — signals as pluggable config (distributed adoption)

**Decision: a new intent signal is a reviewed config PR, not an engineering deploy.**

The discovery maps moved from a single `displacement_map.json` into `recipes/` — each recipe
(`base_displacement.json`, `config2026_displacement.json`) is a JSON file declaring what to
search (`tool_keywords`, `queries`) and, optionally, how to route what it finds
(`routing_overrides`, e.g. Config-2026's `GEN_PLUGINS`/`AGENT` → `upsell` because those posters
are almost always existing customers). Discovery iterates every **enabled** recipe; metrics
segment **by recipe**, so a bad recipe is visible and revertable.

`recipes.py` validates each recipe at startup against `recipes/schema.json` (hand-rolled,
stdlib-only — no new dep) and **fails loud** on a bad one, naming the file. The crucial property,
enforced in code: a recipe is validated with `additionalProperties:false` and the engine only
ever sees a **normalized** form (`name/enabled/figma_surfaces/routing_overrides/signals`) — so
**a recipe can shape discovery and routing but can never touch the trust gates** (ICP filter,
verbatim gate, verify, richness). They're inherited by every recipe and cannot be bypassed by
config. That's the reusable pattern the JD asks for: a GTM team ships a signal via PR (SalesOps
reviews), inherits the whole trust layer for free, and *cannot* lower the quality bar. See
`docs/ADDING_A_SIGNAL.md`. (The Config-2026 recipe ships `enabled: false` until ~10 golden posts
per surface exist, per its own guidance.)

---

## 5. Compliance posture (a feature, not an afterthought)

LinkedIn scraping crosses LinkedIn's ToS and touches personal data (GDPR/CCPA). The
position is **proceed deliberately, with guardrails**, and be able to speak to it as
judgment rather than recklessness:

- **Cookie-free** managed-auth actors — we never handle a user's LinkedIn session.
- **Human-in-the-loop** — the tool surfaces a signal + suggested angle to a rep; it
  **never auto-DMs** a prospect.
- **No committed PII** — live scrape output is written to `data/*-live.json` and the
  run log, both **gitignored**. The committed repo is synthetic.
- **Provenance everywhere** — every record carries `source` (demo/live); the CRM is
  labeled synthetic; business-impact metrics are left blank and marked
  *"(confirm with real CRM data)"* — never invented.
- **Configurable source** — actor IDs are env vars, so the pipeline isn't welded to
  one scraping method.

---

## 6. JD mapping (explicit)

| JD theme | Where it lives in this repo |
|---|---|
| Trustworthy LLM workflows in production | the entire trust layer (§3) — gates, verify, self-consistency, schema lock |
| Constrain LLM outputs | `posttype.py` + `titles.py` (pre-LLM filters) + json_schema in `classify.py` |
| Build quality checks | `gate.py` + `verify.py` + `richness.py` + golden-set eval in `tests/` |
| Build monitoring | `monitoring.py` + `dashboard.py` — funnel, drift, precision vs golden |
| Track adoption / impact | dashboard impact panel (blank, pending real CRM — not fabricated) |
| Salesforce | `accounts.py` — account match + expansion routing |
| Slack | `notify.py` — per-lead delivery, human-in-the-loop |
| OpenAI/Anthropic | `claude-haiku-4-5` classifier, schema-constrained |
| SQL-shaped data | pydantic records throughout; JSONL run log (a queryable shape) |
| PLG → enterprise expansion / expansion signals | the displacement thesis + expansion-first routing |

---

## 7. What it actually found (live, honest)

The pipeline has run end-to-end on live LinkedIn data many times. Representative
findings (the honesty matters more than the headline):

- **The union works.** Native fuzzy search + Google boolean recovered displacement
  posts native-alone missed — designers debating *Jitter vs After Effects*, a PM
  evaluating *Gamma* against Figma Slides, a Miro→FigJam thread.
- **The gates filter hard, on purpose.** A typical run distills ~90 commenters to a
  handful of surfaced leads and a small review queue, dropping the rest with
  auditable reasons (off-ICP title, classified noise, non-verbatim). That refusal to
  surface noise *is* the product.
- **The gate catches real hallucinations** every live run.
- **Live data found real bugs** (the intern/student/anima/cpo title matches) — caught
  by inspecting drops, then fixed and unit-tested. That loop is the monitoring story.
- **Honest limits:** the highest-engagement "comment for the guide" posts skew toward
  AI-generalist hustle audiences, so yield per post is low and many surfaced
  evidences are thin one-word hand-raises (hence the richness score). Lead *quality*
  is governed by **source selection**, which is why discovery evolved from generic
  "design" queries to **named-competitor displacement** queries.

---

## 8. Limitations & honest gaps

- Capability map is hand-curated and dates with each Config (sync-agent is a
  documented next step).
- LinkedIn keyword search is fuzzy; precision is carried by the code filters, not the
  query — accepted and engineered around.
- Synthetic CRM means live routing is mostly net-new until wired to real Salesforce.
- Self-consistency and richness are deliberately cheap heuristics, not models.
- Thin one-word evidence on lead-magnet posts is real; the human-in-the-loop and
  richness score exist precisely because of it.

---

## 9. Stack

Python · **pydantic** (the trust contract) · **Anthropic `claude-haiku-4-5`**
(classifier, schema-constrained) · **Apify** (LinkedIn post-search, post-comments,
post-detail; Google search — all cookie-free) · **Salesforce** (account match /
expansion routing; synthetic in demo, API integration point for live) · **Slack**
(incoming webhook delivery) · static HTML dashboard. No framework — the orchestration
is plain, inspectable code so every step is auditable.

---

## 10. How to run

```bash
pip install -r requirements.txt

# Demo: zero credentials, synthetic + labeled fixtures, golden-set eval
MODE=demo python pipeline.py
python -m pytest -q

# Live: real LinkedIn data
cp .env.example .env   # add APIFY_TOKEN, ANTHROPIC_API_KEY; SLACK_WEBHOOK_URL optional
export $(grep -v '^#' .env | xargs)
MODE=live python pipeline.py
```

---

## 10a. Scheduled automation — it's a workflow, not a one-off

A GitHub Actions workflow (`.github/workflows/daily-intent-scrape.yml`) runs the whole
pipeline **on a daily cron** (and on manual dispatch). Each run discovers fresh posts,
mines and scores leads, delivers surfaced ones to Slack, and **appends the run's
metrics to the monitoring log** — so lead volume and accuracy are tracked *over time*,
not captured once. It runs on repo secrets (`APIFY_TOKEN`, `ANTHROPIC_API_KEY`,
`SLACK_WEBHOOK_URL`) and no-ops cleanly until they're set. This is the "automated,
monitored AI workflow" shape the role describes — the scrape is a scheduled system, and
the run log is the adoption/monitoring trail.

## 11. File map

```
pipeline.py        orchestrator (the LLM is one bounded step inside it)
discover.py        union retrieval: native + Google, smart boolean filter, enrich, cap
posttype.py        post-type + Figma-displaceability gate (the first gate)
extract.py         cookie-free comments actor, per-post, author dedup
titles.py          deterministic ICP title filter (buyer/user/builder tiers)
classify.py        haiku classifier: schema-locked, post-conditioned, self-consistency
gate.py            verbatim-evidence trust gate
verify.py          praise-mislabel quality check
richness.py        signal-richness grading
accounts.py        Salesforce match + expansion-first routing
notify.py          Slack delivery (human-in-the-loop)
monitoring.py      per-run metrics + run log
dashboard.py       static HTML monitoring view
schema.py          pydantic models — the trust contract
data/              icp_titles · figma_capabilities · displacement_map · sfdc_accounts
                   · golden + demo fixtures   (the swappable domain "knowledge")
tests/             golden-set eval + unit tests for every deterministic layer
```

---

## 12. Reusability — it's a domain-agnostic engine

Nothing in the trust layer, the union retriever, the gates, the routing, or the
monitoring knows what Figma is. "Figma" lives entirely in four data files (capability
map, displacement map, ICP titles, stop-list) plus the demo fixtures. Re-point those
four files and the same engine mines, gates, and routes leads for **any** product
with a displacement story and a buyer committee — which is exactly the test of
whether the trust layer, not the agent, was the real work.
