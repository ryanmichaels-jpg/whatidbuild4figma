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

