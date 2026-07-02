"""ACCOUNT-MATCH + ROUTE: turn a commenter's company into an expansion signal.

This is the PLG -> enterprise expansion motion: match the commenter's company
against Salesforce, then decide what the lead MEANS and WHO should act on it. An
existing paid customer showing design-tool intent elsewhere is a churn/expansion
signal for the Account Owner (AE), not a cold DM to the commenter; a company with
no account is a net-new lead for the territory AE.

Routing reflects Figma's ACTUAL org: Figma runs no SDR function (source: CRO Shaunt
Voskanian, 20Sales podcast, Mar 2026) -- AEs own the full motion including net-new
and expansion. So every human-routed lane here goes to an AE, never an SDR.

Demo mode reads a synthetic, clearly-labeled accounts fixture so the stage runs
zero-cred and is testable. Live mode would query the Salesforce API
(match_account_live). Real customer data is never fabricated.

WHERE THIS LIVES AT FIGMA: the intercept score joins the EXTERNAL intent signal (this
pipeline) with INTERNAL product usage (Snowflake). In Figma's stack that join runs in
Clay -- their orchestration layer -- which reads Snowflake, matches Salesforce, and fires
"playbook functions" to reps. So this module's production surface is a Clay table/webhook
input, not a standalone system: this repo simulates that interface (the `product_signals`
block stands in for the Snowflake read) so the routing reads exactly as it would slotted in.
No Clay integration is built here on purpose -- only the boundary is made explicit.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

import recipes as recipes_mod
from schema import Account, IntentType, PlanTier, ProductSignals, Routing, SignalType

_DATA = os.path.join(os.path.dirname(__file__), "data", "sfdc_accounts.json")

# dbt read-back: a snapshot of the warehouse account_heat.sql model, if the warehouse produced
# one. Optional by design -- absent file means identical behavior to a pipeline with no warehouse.
_HEAT_SNAP = os.path.join(os.path.dirname(__file__), "data", "warehouse", "account_heat_snapshot.json")
_HEAT_ESCALATE = float(os.environ.get("ACCOUNT_HEAT_ESCALATE", "5.0"))


def _account_heat() -> dict:
    try:
        with open(_HEAT_SNAP, "r", encoding="utf-8") as fh:
            return {_normalize(k): v for k, v in json.load(fh).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

_LEGAL_SUFFIXES = {"inc", "inc.", "llc", "ltd", "ltd.", "co", "co.", "corp", "corp.", "gmbh", "plc", "the"}


def _normalize(company: str) -> str:
    text = (company or "").lower().strip()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    tokens = [t for t in text.split() if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


@lru_cache(maxsize=1)
def _fixture() -> list[dict]:
    with open(_DATA, "r", encoding="utf-8") as fh:
        return json.load(fh)["accounts"]


def match_account_demo(company: str) -> Account:
    """Match a company against the synthetic Salesforce fixture."""
    norm = _normalize(company)
    if norm:
        for acct in _fixture():
            names = {_normalize(acct["account_name"]), *(_normalize(a) for a in acct.get("aliases", []))}
            if norm in names:
                ps = acct.get("product_signals")
                return Account(
                    query_company=company,
                    matched=True,
                    account_name=acct["account_name"],
                    is_customer=acct["is_customer"],
                    plan=PlanTier(acct["plan"]),
                    seats=acct.get("seats"),
                    arr_usd=acct.get("arr_usd"),
                    account_owner=acct.get("account_owner"),
                    product_signals=ProductSignals(**ps) if ps else None,
                    source="demo",
                )
    return Account(query_company=company, matched=False, source="demo")


def match_account_live(company: str) -> Account:
    """Match against real Salesforce. Integration point for live CRM data.

    Wire with the Salesforce REST API (SOQL on Account by name/domain) using
    SALESFORCE_* credentials. Until wired, fall back to the synthetic fixture so the
    live pipeline still runs, and label the source so nothing reads as real CRM data.
    """
    if not os.environ.get("SALESFORCE_INSTANCE_URL"):
        acct = match_account_demo(company)
        acct.source = "demo-fallback"  # not real Salesforce data
        return acct
    raise NotImplementedError(
        "Salesforce API matching not wired yet; set SALESFORCE_* and implement the SOQL query here."
    )


def match_account(company: str | None, mode: str = "demo") -> Account | None:
    if not company:
        return None
    return match_account_live(company) if mode == "live" else match_account_demo(company)


_STRONG_INTENT = {IntentType.active_need, IntentType.evaluating}

# Figma's money is expansion (NDR 139%, AEs own expansion, no CS team), so we split the
# pipeline into two lanes: existing-customer signals vs net-new logos.
_EXPANSION_SIGNALS = {SignalType.upsell, SignalType.expansion, SignalType.churn_risk}


def lane(signal_type: SignalType | None) -> str:
    """Which pipeline lane a routed lead belongs to: expansion / net-new / unknown."""
    if signal_type in _EXPANSION_SIGNALS:
        return "expansion"
    if signal_type == SignalType.net_new:
        return "net-new"
    return "unknown"


def route(intent_type: IntentType | None, account: Account | None, company: str | None,
          recipe_surface: str | None = None) -> Routing:
    """Expansion-first routing, then a stack-aware INTERCEPT pass, then any recipe override.

    The base route decides signal/priority/recipient from the CRM match. The intercept pass
    then joins the EXTERNAL intent signal with INTERNAL product usage -- the exact join Figma
    runs in Clay over Snowflake -- to decide *timing*: escalate an active need at an account
    whose seats are already growing (expansion-ready), and cool a merely-curious lead at a
    heavy-usage account into a nurture, not a call. Every lead gets a one-line "why now".
    """
    base = _base_route(intent_type, account, company)
    routed = _apply_intercept(base, intent_type, account)
    return _apply_recipe_override(routed, recipe_surface, account)


def _apply_recipe_override(routing: Routing, recipe_surface: str | None, account: Account | None) -> Routing:
    """Let a recipe re-aim routing for its own surface (e.g. GEN_PLUGINS/AGENT -> UPSELL for
    existing customers). Only re-aims EXISTING-customer leads; never overrides the trust gates."""
    if not (account and account.matched and account.is_customer):
        return routing
    ov = recipes_mod.routing_override(recipe_surface)
    if ov:
        try:
            routing.signal_type = SignalType(ov)
        except ValueError:
            return routing
        routing.recipient = f"AE: {account.account_owner or 'Account Owner'}"
        routing.rationale += f" | recipe override ({recipe_surface} -> {ov})"
    return routing


def _why_now(intent_type: IntentType | None, account: Account | None) -> str:
    """One-line intent x product-signal summary for the rep."""
    it = intent_type.value if intent_type else "unknown-intent"
    ps = account.product_signals if account else None
    if account and account.is_customer and ps:
        parts = []
        if ps.pro_seats is not None:
            parts.append(f"{ps.pro_seats} Pro seats")
        if ps.seat_growth_90d_pct is not None:
            parts.append(f"{ps.seat_growth_90d_pct:+.0f}% seats/90d")
        if ps.feature_adoption:
            parts.append("uses " + ", ".join(ps.feature_adoption))
        ctx = "; ".join(parts) if parts else "existing customer"
        return f"{it} at an account with {ctx}"
    return f"{it}; no product footprint (net-new)"


def _apply_intercept(base: Routing, intent_type: IntentType | None, account: Account | None) -> Routing:
    """Deterministic intent x usage rules (documented, no LLM). Adjusts timing only."""
    base.why_now = _why_now(intent_type, account)
    ps = account.product_signals if (account and account.is_customer) else None
    growing = bool(ps and (ps.seat_growth_90d_pct or 0) > 0)
    heavy = bool(ps and (ps.pro_seats or 0) >= 100 and (ps.last_active_days is None or ps.last_active_days <= 14))

    if intent_type == IntentType.active_need and growing:
        # expansion-ready + warm: escalate one priority tier
        base.priority = max(0, base.priority - 1)
        base.rationale += " | intercept: seats already growing -- expansion-ready, escalated a tier"
    elif intent_type == IntentType.curious and heavy:
        # curious but already a heavy user: nurture/insight, not a call task
        base.signal_type = SignalType.expansion
        base.priority = 3
        base.rationale += " | intercept: curious but heavy usage -- nurture/insight, not a call"
    # active_need + no product footprint -> standard net-new (base already correct)

    # dbt read-back (the dashed arrow): a hot account from account_heat.sql escalates priority by
    # at most ONE tier. Missing snapshot -> no effect, identical to a pipeline with no warehouse.
    if account and account.matched:
        heat = _account_heat().get(_normalize(account.account_name or account.query_company or ""))
        if heat is not None and heat >= _HEAT_ESCALATE:
            base.priority = max(0, base.priority - 1)
            base.rationale += f" | account_heat {heat:.1f} (dbt read-back) -- escalated"
            if base.why_now:
                base.why_now += f"; account heat {heat:.1f}"
    return base


def _base_route(intent_type: IntentType | None, account: Account | None, company: str | None) -> Routing:
    """Expansion-first routing: decide signal type, priority (0=highest), and recipient."""
    if not company:
        return Routing(
            signal_type=SignalType.enrich,
            priority=3,
            recipient="Territory AE (enrich first)",
            rationale="no company captured on the profile; enrich before routing",
        )

    if account and account.matched and account.is_customer:
        owner = account.account_owner or "Account Owner"
        seats = f"{account.seats} seats" if account.seats else "unknown seats"
        if account.plan in (PlanTier.enterprise, PlanTier.org):
            if intent_type in _STRONG_INTENT:
                return Routing(
                    signal_type=SignalType.churn_risk,
                    priority=0,
                    recipient=f"AE: {owner}",
                    rationale=(
                        f"existing {account.plan.value} customer ({seats}) showing design-tool "
                        f"intent elsewhere -- expansion/churn risk; engage the buyer via the AE"
                    ),
                )
            return Routing(
                signal_type=SignalType.expansion,
                priority=2,
                recipient=f"AE: {owner}",
                rationale=f"existing {account.plan.value} customer ({seats}); soft expansion signal",
            )
        # free / pro -> product-led upsell
        return Routing(
            signal_type=SignalType.upsell,
            priority=1,
            recipient=f"AE: {owner}",
            rationale=f"PLG {account.plan.value} customer ({seats}) -- upsell / seat expansion",
        )

    if account and account.matched and not account.is_customer:
        return Routing(
            signal_type=SignalType.net_new,
            priority=1,
            recipient=f"Territory AE: {account.account_owner or 'prospecting'}",
            rationale=f"known account '{account.account_name}', not yet a customer -- net-new",
        )

    return Routing(
        signal_type=SignalType.net_new,
        priority=2,
        recipient="Territory AE (net-new)",
        rationale=f"no Salesforce account for '{company}' -- net-new company",
    )
