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
