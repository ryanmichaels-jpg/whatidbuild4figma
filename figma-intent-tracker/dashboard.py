"""DASHBOARD stage: a static HTML monitoring view.

Tracks the trust layer's health, not vanity metrics: the funnel
(extracted -> title-filtered -> classified -> surfaced/review/dropped), the
persona and intent breakdowns, and precision vs the golden set. Business-impact
metrics are left blank and marked '(confirm with real CRM data)' -- never fabricated.
"""
from __future__ import annotations

import html
import os
from collections import Counter

from schema import Decision, Lead

_OUT = os.path.join(os.path.dirname(__file__), "dashboard.html")


def _bar(label: str, value: int, total: int) -> str:
    pct = (value / total * 100) if total else 0
    return (
        f'<div class="row"><span class="lbl">{html.escape(label)}</span>'
        f'<span class="track"><span class="fill" style="width:{pct:.0f}%"></span></span>'
        f'<span class="val">{value}</span></div>'
    )


def render(leads: list[Lead], mode: str, post_results: dict | None = None) -> str:
    from pipeline import funnel as _funnel, precision_vs_golden

    f = _funnel(leads)
    total = f["extracted"] or 1

    # post-type gate rollup
    post_results = post_results or {}
    post_types = Counter(pc.post_type.value for pc in post_results.values())
    posts_total = len(post_results) or 1
    posts_qualified = sum(1 for pc in post_results.values() if pc.qualifies)
    post_html = "".join(_bar(k, v, posts_total) for k, v in sorted(post_types.items())) or "<em>n/a</em>"

    # quality counters
    hallucinations = sum(1 for x in leads if "verbatim" in x.reason)
    downgrades = sum(1 for x in leads if x.quality_flag and x.quality_flag != "thin_handraise")

    personas = Counter(
        x.title.persona.value for x in leads if x.title.persona is not None
    )
    intents = Counter(
        x.classification.intent_type.value for x in leads if x.classification is not None
    )
    prec = precision_vs_golden(leads)

    def _acct_cell(x):
        a = x.account
        if a and a.matched:
            cust = "customer" if a.is_customer else "prospect"
            seats = f" / {a.seats} seats" if a.seats else ""
            return f"{html.escape(a.account_name or '')} ({a.plan.value} {cust}{seats})"
        if a:
            return "net-new"
        return ""

    def _signal_cell(x):
        r = x.routing
        return f"P{r.priority} {r.signal_type.value}" if r else ""

    surfaced_rows = ""
    # richest-signal leads first -- a rep should see substantive comments before bare hand-raises
    surfaced = sorted(
        (x for x in leads if x.decision == Decision.surface),
        key=lambda x: x.richness or 0, reverse=True,
    )
    for x in surfaced:
        c, cls = x.commenter, x.classification
        route = x.routing.recipient if x.routing else ""
        surfaced_rows += (
            "<tr>"
            f"<td>{html.escape(c.name)}</td>"
            f"<td>{html.escape(c.headline or '')}</td>"
            f"<td>{html.escape(c.company or '')}</td>"
            f"<td>{html.escape(_acct_cell(x))}</td>"
            f"<td>{html.escape(_signal_cell(x))}</td>"
            f"<td>{html.escape(x.richness_label or '')}</td>"
            f"<td>{html.escape(route)}</td>"
            f"<td>{x.title.persona.value}/{cls.intent_type.value} {cls.confidence:.2f}</td>"
            f'<td class="q">"{html.escape(cls.evidence_quote)}"</td>'
            "</tr>"
        )

    # account-routing rollups across actionable (surface/review) leads
    routed = [x for x in leads if x.routing is not None]
    signals = Counter(x.routing.signal_type.value for x in routed)
    customer_split = Counter(
        ("existing customer" if (x.account and x.account.is_customer)
         else "net-new/prospect" if x.account else "no company")
        for x in routed
    )
    routing_html = (
        "".join(_bar(k, v, len(routed) or 1) for k, v in sorted(signals.items())) or "<em>none</em>"
    )
    customer_html = (
        "".join(_bar(k, v, len(routed) or 1) for k, v in sorted(customer_split.items())) or "<em>none</em>"
    )

    funnel_html = "".join(
        [
            _bar("Extracted (commenters)", f["extracted"], total),
            _bar("Passed ICP title filter", f["title_filtered_in"], total),
            _bar("Classified by LLM", f["classified"], total),
            _bar("Surfaced", f["surfaced"], total),
            _bar("Review", f["review"], total),
            _bar("Dropped", f["dropped"], total),
        ]
    )
    persona_html = "".join(_bar(k, v, total) for k, v in sorted(personas.items())) or "<em>none</em>"
    intent_html = "".join(_bar(k, v, total) for k, v in sorted(intents.items())) or "<em>none</em>"

    if prec:
        sp = "n/a" if prec["surface_precision"] is None else f"{prec['surface_precision']:.0%}"
        eval_html = (
            f"<p>Labeled examples: {prec['labeled']}<br>"
            f"Decision accuracy vs golden: <b>{prec['accuracy']:.0%}</b><br>"
            f"Surface precision: <b>{sp}</b></p>"
        )
    else:
        eval_html = "<p><em>No golden labels for this run.</em></p>"

    return _write(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Figma Intent Miner -- Monitoring</title>
<style>
 body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:40px;color:#1a1a1a;max-width:980px}}
 h1{{font-size:20px}} h2{{font-size:15px;margin-top:28px;border-bottom:1px solid #eee;padding-bottom:4px}}
 .meta{{color:#666;font-size:12px}}
 .row{{display:flex;align-items:center;margin:4px 0}}
 .lbl{{width:200px}} .val{{width:36px;text-align:right;font-variant-numeric:tabular-nums}}
 .track{{flex:1;background:#f0f0f0;border-radius:3px;height:14px;margin:0 8px;overflow:hidden}}
 .fill{{display:block;height:100%;background:#0d99ff}}
 table{{border-collapse:collapse;width:100%;margin-top:8px;font-size:12.5px}}
 th,td{{border:1px solid #e5e5e5;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#fafafa}} .q{{color:#0a7d3f}}
 .note{{background:#fff8e6;border:1px solid #f0e0a8;padding:10px 12px;border-radius:6px}}
</style></head><body>
<h1>Figma LinkedIn Intent Miner -- Monitoring</h1>
<p class="meta">Mode: <b>{html.escape(mode)}</b> &middot; The trust layer is the product: every surfaced lead carries a verbatim evidence quote that passed a deterministic gate.</p>

<h2>Post-type gate</h2>
<p class="meta">{posts_qualified} of {len(post_results)} posts qualified (lead_magnet / tool_question / tool_comparison). Showcases and off_topic posts are dropped before any comment is mined.</p>{post_html}

<h2>Funnel</h2>{funnel_html}
<h2>Quality checks</h2>
<p>Hallucinated quotes caught by the gate: <b>{hallucinations}</b><br>
Praise-mislabels downgraded by verification: <b>{downgrades}</b></p>
<h2>Persona breakdown (ICP tiers)</h2>{persona_html}
<h2>Intent breakdown</h2>{intent_html}
<h2>Quality vs golden set</h2>{eval_html}

<h2>Account routing (Salesforce match)</h2>
<p class="meta">Across actionable (surfaced + review) leads. Synthetic accounts in demo mode; Salesforce API in live.</p>
<b>Signal type</b>{routing_html}
<b>Customer vs net-new</b>{customer_html}

<h2>Surfaced leads ({f['surfaced']})</h2>
<table><tr><th>Name</th><th>Headline</th><th>Company</th><th>Salesforce account</th><th>Signal</th><th>Richness</th><th>Route to</th><th>Persona/Intent</th><th>Evidence (verbatim)</th></tr>
{surfaced_rows or '<tr><td colspan="9"><em>none</em></td></tr>'}
</table>

<h2>Business impact</h2>
<div class="note">
 Meetings booked from surfaced leads: <b>__</b> (confirm with real CRM data)<br>
 Pipeline influenced: <b>__</b> (confirm with real CRM data)<br>
 Rep adoption / acted-on rate: <b>__</b> (confirm with real CRM data)
</div>
</body></html>"""
    )


def _write(doc: str) -> str:
    with open(_OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return _OUT
