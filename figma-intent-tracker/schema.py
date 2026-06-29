"""Pydantic schemas: the trust contract.

Every cross-stage object is a validated model. The LLM classifier is
schema-constrained (see classify.py) so it cannot omit a required field, and the
gate (gate.py) refuses to surface any lead whose evidence_quote is not a verbatim
substring of the real comment.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Persona(str, Enum):
    """Figma buyer-committee tiers (from public case studies + enterprise framing).

    `builder` is a looser prospect tier -- founders/PMs/indie/no-code builders who
    are in-market for a design tool but aren't a classic design role. Builders never
    auto-surface; the gate routes them to human review.
    """

    champion = "champion"
    economic_buyer = "economic_buyer"
    user = "user"
    gatekeeper = "gatekeeper"
    builder = "builder"


class IntentType(str, Enum):
    active_need = "active_need"
    evaluating = "evaluating"
    curious = "curious"
    noise = "noise"


class Decision(str, Enum):
    surface = "surface"
    review = "review"
    drop = "drop"


class TitleStatus(str, Enum):
    matched = "matched"      # include rule hit -> persona assigned -> eligible for LLM
    excluded = "excluded"    # exclude rule hit (student/recruiter/intern...) -> drop, no LLM
    off_icp = "off_icp"      # title present but no buyer/user persona -> drop, no LLM
    missing = "missing"      # no headline -> route to human review, never a silent drop


class Commenter(BaseModel):
    """A person who commented on an intent post. Raw extraction or synthetic fixture."""

    name: str
    headline: Optional[str] = None
    profile_url: Optional[str] = None
    comment_text: str
    reaction: Optional[str] = None
    timestamp: Optional[str] = None
    post_url: Optional[str] = None
    source: str = "demo"  # provenance: "demo" (synthetic) or "live" (scraped)


class TitleResult(BaseModel):
    """Output of the deterministic ICP title filter."""

    status: TitleStatus
    persona: Optional[Persona] = None
    matched_keyword: Optional[str] = None


class Classification(BaseModel):
    """Schema-constrained LLM output. All fields required so the model cannot omit any."""

    intent_type: IntentType
    need: str = Field(..., description="One sentence summarizing the stated need.")
    evidence_quote: str = Field(
        ..., description="A verbatim substring copied from the comment. No paraphrasing."
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    suggested_angle: str = Field(
        ..., description="One-line rep talking point. Use only what the comment states."
    )


class Lead(BaseModel):
    """A commenter after the full pipeline: title filter -> (classify) -> gate."""

    commenter: Commenter
    title: TitleResult
    classification: Optional[Classification] = None  # None when dropped/reviewed before the LLM
    decision: Decision
    reason: str


def classification_json_schema() -> dict:
    """Flat JSON Schema for the Anthropic structured-output config.

    Hand-built (rather than pydantic's model_json_schema) to keep enums inline and
    set additionalProperties:false, which is what the API's json_schema format expects.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "intent_type",
            "need",
            "evidence_quote",
            "confidence",
            "suggested_angle",
        ],
        "properties": {
            "intent_type": {
                "type": "string",
                "enum": [e.value for e in IntentType],
                "description": "active_need: actively building/seeking a design or UI workflow now; evaluating: comparing or trying design/AI tools; curious: passive interest, no project; noise: praise/off-topic/not about doing design work.",
            },
            "need": {"type": "string", "description": "One sentence summarizing the stated need."},
            "evidence_quote": {
                "type": "string",
                "description": "A verbatim substring copied exactly from the comment. Do not paraphrase or invent.",
            },
            # range enforced by pydantic after parsing; the API rejects min/max on numbers
            "confidence": {"type": "number", "description": "Confidence from 0.0 to 1.0."},
            "suggested_angle": {
                "type": "string",
                "description": "One-line rep talking point grounded only in what the comment says.",
            },
        },
    }
