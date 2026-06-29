from schema import (
    Classification,
    Commenter,
    Decision,
    IntentType,
    Lead,
    Persona,
    TitleResult,
    TitleStatus,
)
from verify import looks_like_praise, verify


def test_looks_like_praise():
    assert looks_like_praise("love this, so true -- numbers don't lie")
    assert looks_like_praise("amazing work! 🔥")
    # has a real tooling-intent signal -> not praise
    assert not looks_like_praise("love this tool, we're switching from Figma")
    assert not looks_like_praise("we're comparing options for our team")


def _surfaced_lead(quote, comment):
    cls = Classification(
        intent_type=IntentType.active_need, need="n", evidence_quote=quote,
        confidence=0.9, suggested_angle="a",
    )
    title = TitleResult(status=TitleStatus.matched, persona=Persona.user, matched_keyword="product designer")
    return Lead(
        commenter=Commenter(name="X", headline="Product Designer", comment_text=comment),
        title=title, classification=cls, decision=Decision.surface, reason="surfaced",
    )


def test_verify_downgrades_praise_surface_to_review():
    lead = _surfaced_lead("love this, so true", "love this, so true -- numbers don't lie")
    decision, flag = verify(lead)
    assert decision == Decision.review
    assert flag and "praise" in flag


def test_verify_keeps_real_intent_surface():
    lead = _surfaced_lead("we're comparing options", "we're comparing options for our team")
    decision, flag = verify(lead)
    assert decision == Decision.surface
    assert flag is None
