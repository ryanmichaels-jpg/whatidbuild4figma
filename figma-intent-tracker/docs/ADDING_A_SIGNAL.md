# Adding a signal (without an engineer)

A "signal" is a way of finding in-market people — e.g. "people fighting with After Effects,"
or a whole Config-2026 feature map. Signals are **config, not code**: you ship one by adding a
**recipe JSON** to `recipes/` and opening a PR. No deploy, no engineer in the loop.

## The 4 steps

1. **Write a recipe JSON** in `recipes/` (copy `base_displacement.json` or
   `config2026_displacement.json` as a template). Required envelope:
   ```json
   {
     "name": "my_signal",
     "version": "1.0",
     "enabled": false,
     "figma_surfaces": ["sites"],
     "routing_overrides": { "sites": "upsell" },
     "surfaces": { "sites": { "tool_keywords": ["webflow"], "queries": ["Webflow build guide comment"] } }
   }
   ```
   (Use a `features` array instead of `surfaces` for the richer Config-2026 shape.)
2. **Open a PR.** **SalesOps reviews it** — the review is about *targeting and routing*, not code.
3. **Ship disabled, then flip `enabled: true`** once there are ~10 labeled golden posts for its
   surfaces (so precision is measurable from day one).
4. **Watch the dashboard.** Metrics segment **by recipe**, so if a recipe surfaces junk it's
   visible immediately and you revert the PR.

## What a recipe CAN and CANNOT do

**Can:** declare what to search (`tool_keywords`, `queries`) and, optionally, how to route the
leads it surfaces (`routing_overrides`, e.g. GEN_PLUGINS/AGENT → `upsell` because those posters
are almost always existing customers).

**Cannot — by design:** touch the trust gates. A recipe is validated against
`recipes/schema.json` with `additionalProperties: false`, and the engine only ever sees a
**normalized** form (`{name, enabled, figma_surfaces, routing_overrides, signals}`) — the
documentation sections never reach engine code. So the **ICP filter, verbatim gate, verify, and
richness gates are inherited automatically and cannot be bypassed or weakened by config.** That
is the whole point of the pattern: a GTM team can ship a new signal and *cannot* lower the
quality bar. A malformed recipe **fails loudly at startup** (names the file + the problem) — it
never silently skips.

## Why this is the reusable pattern the JD asks for

"Reusable patterns that enable distributed adoption rather than central dependency." The trust
layer is built once; every new signal inherits it for free. The mechanism to add one is a
reviewed config change any GTM team can make — the engineer owns the gates, not the growth ideas.
