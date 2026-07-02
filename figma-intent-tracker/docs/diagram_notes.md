# Diagram notes (for the tldraw canvas)

One short paragraph per change, written so it can be transferred straight onto the
board: what the node/box says, where its arrows go, and what it throws away.

---

## Change 1 — Routing reflects Figma's real org (no SDRs)

**Box to update:** the "Route (Salesforce)" node's output branches. The old NET-NEW
branch said "→ SDR". Rename it to **"→ Territory AE (net-new)"**. All three routing
outputs now point to an **AE**: UPSELL/CHURN-EXP → Account Owner AE, NET-NEW →
territory AE. Add a small caption under the Route node: *"Figma runs no SDR function
(CRO, 20Sales podcast) — AEs own the full motion, net-new + expansion."* Nothing about
the arrows into Slack changes; this is a relabel that makes the routing match the actual
customer instead of a generic B2B org. It throws away nothing new — it corrects who the
kept leads are handed to.

---

## Change 2 — CRM hygiene as a byproduct (new parallel branch)

**New box:** a green "CRM Hygiene" node hanging off the **Extract commenters** node (or the
ICP filter), on a *separate* rail from the main scoring spine. Its caption: *"diff scraped
title/company vs Salesforce contact -- flag stale records, 0 tokens."* It does **not** feed
the Route node; it feeds two new outputs at the bottom: a **"Hygiene review queue"** store
box and a **"Slack: hygiene digest"** output box (one digest per run, not per lead). Draw a
thin dashed line from the main Slack card to a small tag "⚠ stale-record line" to show a
surfaced lead's card can carry a hygiene note. The key visual point: this branch **runs
alongside** the trust chain and never touches it — one data source (the scrape), two
workflows (leads + CRM hygiene). What it throws away: nothing; it *adds* a free output.

---

## Change 3 — Intercept score (intent × product signal)

**Node to add:** a small violet input box to the LEFT of the "Route (Salesforce)" node,
labeled **"Snowflake product signals (via Clay)"** — Pro seats, seat growth, feature
adoption. Draw an arrow from it INTO the Route node so Route now has two inputs: the intent
(from the trust chain) and the usage signal. Relabel Route's caption: *"intent × usage
intercept — escalate expansion-ready, cool curious-heavy to nurture."* Add a "Why now" tag
on the arrow from Route → Slack (e.g. "300 Pro seats, +38%/90d"). Put a dashed boundary box
around the Snowflake/Clay node labeled *"production surface = Clay table/webhook (simulated
here)"* so it's clear no Clay integration is built. It throws away nothing; it sharpens
*timing* — which of the kept leads a rep should call today.

---

## Change 4 — Adoption feedback loop (the return arrow)

**New arrows, closing the loop.** On the Slack card box, add a footer chip: **"👍 booked ·
👎 bad lead · 🔁 wrong route."** Then draw a NEW return arrow from Slack back UP to the
Monitor box labeled **"rep reactions."** From Monitor, add two outputs: (1) a relabel of the
Monitor node's top metric to **"Rep action rate (acted/surfaced)"** — now the headline number,
above precision; and (2) a dashed arrow from Monitor to a small store box **"golden_candidates
→ golden set"** with a curving arrow back to the "Classify/Gate" region captioned *"reps label
→ golden grows → gates retune."* This is the only arrow on the whole board that points
*backward* — the feedback loop. It throws away nothing; it teaches the system what to throw
away next time.

---

## Change 5 — Governance & rollout (a framing card, not a pipeline box)

**Not a node — a card in the corner** titled **"Rollout & Governance."** Three tight lines:
*"Pilot 1 AE pod (5 reps, 2 wks) → gate: action ≥50% & precision ≥85% → expand pod-by-pod."*
Below it a tiny owner strip: **SalesOps** (routing) · **Enablement** (rep feedback) · **GTM
Systems** (secrets/infra) · **Me** (engine). And a red **kill-switch** tag: *"revoke
APIFY_TOKEN → pipeline no-ops."* This card tells the interviewer you thought about production
adoption, not just the code. See `GOVERNANCE.md`.

