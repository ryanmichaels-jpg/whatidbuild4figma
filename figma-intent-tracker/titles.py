"""Deterministic ICP title filter -- the 'constrain outputs' layer.

Runs BEFORE any LLM call. Off-ICP commenters are dropped for free (no tokens
spent), buyer/user personas pass to the classifier, and a missing headline is
routed to human review rather than silently dropped.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from schema import Persona, TitleResult, TitleStatus

_DATA = os.path.join(os.path.dirname(__file__), "data", "icp_titles.json")

# HR/people-leadership signals: under these, never assign the economic_buyer persona
# (a "Chief People Officer" / "Fractional CPO | HR" is not a product/eng buyer).
_HR_CONTEXT = [
    "chief people officer", "people officer", "head of people", "people & culture",
    "people and culture", "human resources", "chro", "fractional cpo", "people ops",
]


@lru_cache(maxsize=1)
def _rules() -> dict:
    with open(_DATA, "r", encoding="utf-8") as fh:
        return json.load(fh)


def classify_title(headline: str | None) -> TitleResult:
    """Map a LinkedIn headline to a TitleResult.

    Precedence: missing -> excluded -> include-match -> off_icp.
    Include rules are checked in file order, so more specific personas (e.g. a
    'director of product design' champion) win over broader ones.
    """
    if headline is None or not headline.strip():
        return TitleResult(status=TitleStatus.missing)

    text = headline.lower()
    rules = _rules()

    for term in rules["exclude"]:
        if term in text:
            return TitleResult(status=TitleStatus.excluded, matched_keyword=term)

    exceptions = rules.get("exclude_token_exceptions", {})
    for token in rules["exclude_tokens"]:
        # whole-word match so 'intern' does not fire on 'internal' or 'international'.
        # An exception list lets e.g. 'student support'/'student success' (a service
        # area) avoid the 'student' (job-seeker) exclude via negative lookahead.
        exc = exceptions.get(token)
        pat = rf"\b{re.escape(token)}\b"
        if exc:
            pat += rf"(?!\s+(?:{'|'.join(re.escape(e) for e in exc)}))"
        if re.search(pat, text):
            return TitleResult(status=TitleStatus.excluded, matched_keyword=token)

    # "CPO" is ambiguous (Chief Product vs Chief People Officer), so we require the
    # full "chief product officer" and never assign the economic_buyer persona under
    # HR/people context -- an HR leader is not a product/eng buyer.
    hr_context = any(term in text for term in _HR_CONTEXT)

    for rule in rules["include"]:
        if rule["persona"] == "economic_buyer" and hr_context:
            continue
        for kw in rule["keywords"]:
            if kw in text:
                return TitleResult(
                    status=TitleStatus.matched,
                    persona=Persona(rule["persona"]),
                    matched_keyword=kw,
                )

    return TitleResult(status=TitleStatus.off_icp)
