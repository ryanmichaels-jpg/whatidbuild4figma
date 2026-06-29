"""NOTIFY stage: deliver a surfaced lead to a rep via Slack.

Human-in-the-loop: this posts a signal plus a suggested angle for a person to act
on. It never auto-DMs the prospect. With no SLACK_WEBHOOK_URL set (e.g. the demo),
it prints the exact payload instead of sending.
"""
from __future__ import annotations

import json
import os

import urllib.request

from schema import Lead


def build_payload(lead: Lead) -> dict:
    c = lead.commenter
    cls = lead.classification
    persona = lead.title.persona.value if lead.title.persona else "unknown"
    r = lead.routing
    acct = lead.account

    header = f"*New design-tool signal* ({persona} / {cls.intent_type.value}, conf {cls.confidence:.2f})"
    if r:
        header = f"*[P{r.priority}] {r.signal_type.value.upper()} signal* ({persona} / {cls.intent_type.value}, conf {cls.confidence:.2f})"

    lines = [
        header,
        f"*{c.name}* -- {c.headline or 'no title'}",
        f"Company: {c.company or 'unknown'}",
    ]
    if acct and acct.matched:
        plan = acct.plan.value
        seats = f", {acct.seats} seats" if acct.seats else ""
        arr = f", ${acct.arr_usd:,} ARR" if acct.arr_usd else ""
        cust = "customer" if acct.is_customer else "not a customer"
        lines.append(f"Salesforce: {acct.account_name} ({plan} {cust}{seats}{arr})")
    elif acct:
        lines.append("Salesforce: no account match (net-new)")
    if r:
        lines.append(f"Route to: {r.recipient}  --  {r.rationale}")
    lines += [
        f"Need: {cls.need}",
        f"Evidence (verbatim): \"{cls.evidence_quote}\"",
        f"Suggested angle: {cls.suggested_angle}",
        f"Profile: {c.profile_url or 'n/a'}  |  Post: {c.post_url or 'n/a'}",
    ]
    return {"text": "\n".join(lines)}


def notify(lead: Lead) -> dict:
    """Send to Slack if configured, otherwise print the payload (demo). Returns the payload."""
    payload = build_payload(lead)
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("[notify:demo] would POST to Slack:")
        print(payload["text"])
        return payload
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted webhook URL)
        resp.read()
    return payload
