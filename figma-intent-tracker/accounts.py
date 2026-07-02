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
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from schema import Account, IntentType, PlanTier, Routing, SignalType

_DATA = os.path.join(os.path.dirname(__file__), "data", "sfdc_accounts.json")

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
                return Account(
                    query_company=company,
                    matched=True,
                    account_name=acct["account_name"],
                    is_customer=acct["is_customer"],
                    plan=PlanTier(acct["plan"]),
                    seats=acct.get("seats"),
                    arr_usd=acct.get("arr_usd"),
                    account_owner=acct.get("account_owner"),
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


def route(intent_type: IntentType | None, account: Account | None, company: str | None) -> Routing:
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
