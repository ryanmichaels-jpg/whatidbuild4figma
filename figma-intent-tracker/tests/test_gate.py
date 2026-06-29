from gate import decide, is_verbatim
from schema import (
    Classification,
    Commenter,
    Decision,
    IntentType,
    Persona,
    TitleResult,
    TitleStatus,
)


def _commenter(text):
    return Commenter(name="X", headline="Product Designer", comment_text=text)


def _title():
    return TitleResult(status=TitleStatus.matched, persona=Persona.user, matched_keyword="product designer")


def _cls(intent, conf, quote):
    return Classification(
        intent_type=intent, need="n", evidence_quote=quote, confidence=conf, suggested_angle="a"
    )


def test_is_verbatim():
    assert is_verbatim("comparing options", "we're comparing options for our team")
    assert not is_verbatim("we are leaving Figma", "we're comparing options for our team")
    assert not is_verbatim("", "anything")


def test_surface_requires_intent_and_confidence():
    c = _commenter("we're comparing options now")
    d, _ = decide(c, _title(), _cls(IntentType.evaluating, 0.8, "comparing options"))
    assert d == Decision.surface


def test_low_confidence_routes_to_review():
    c = _commenter("we're comparing options now")
    d, _ = decide(c, _title(), _cls(IntentType.evaluating, 0.4, "comparing options"))
    assert d == Decision.review


def test_curious_routes_to_review():
    c = _commenter("curious what is out there")
    d, _ = decide(c, _title(), _cls(IntentType.curious, 0.9, "curious what is out there"))
    assert d == Decision.review


def test_noise_drops():
    c = _commenter("love this post")
    d, _ = decide(c, _title(), _cls(IntentType.noise, 0.2, "love this post"))
    assert d == Decision.drop


def test_hallucinated_quote_is_dropped_even_at_high_confidence():
    # the gate must override a confident classification when the quote is not real
    c = _commenter("We migrated about half our teams already this spring.")
    d, reason = decide(c, _title(), _cls(IntentType.evaluating, 0.95, "we are leaving Figma next month"))
    assert d == Decision.drop
    assert "verbatim" in reason
