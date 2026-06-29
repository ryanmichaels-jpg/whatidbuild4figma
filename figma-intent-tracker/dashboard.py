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


def render(leads: list[Lead], mode: str) -> str:
    from pipeline import funnel as _funnel, precision_vs_golden

    f = _funnel(leads)
    total = f["extracted"] or 1

    personas = Counter(
        x.title.persona.value for x in leads if x.title.persona is not None
    )
    intents = Counter(
        x.classification.intent_type.value for x in leads if x.classification is not None
    )
    prec = precision_vs_golden(leads)

    surfaced_rows = ""
    for x in leads:
        if x.decision != Decision.surface:
            continue
        c, cls = x.commenter, x.classification
        surfaced_rows += (
            "<tr>"
            f"<td>{html.escape(c.name)}</td>"
            f"<td>{html.escape(c.headline or '')}</td>"
            f"<td>{x.title.persona.value}</td>"
            f"<td>{cls.intent_type.value}</td>"
            f"<td>{cls.confidence:.2f}</td>"
            f'<td class="q">"{html.escape(cls.evidence_quote)}"</td>'
            f"<td>{html.escape(cls.suggested_angle)}</td>"
            "</tr>"
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

<h2>Funnel</h2>{funnel_html}
<h2>Persona breakdown (ICP tiers)</h2>{persona_html}
<h2>Intent breakdown</h2>{intent_html}
<h2>Quality vs golden set</h2>{eval_html}

<h2>Surfaced leads ({f['surfaced']})</h2>
<table><tr><th>Name</th><th>Headline</th><th>Persona</th><th>Intent</th><th>Conf</th><th>Evidence (verbatim)</th><th>Suggested angle</th></tr>
{surfaced_rows or '<tr><td colspan="7"><em>none</em></td></tr>'}
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
