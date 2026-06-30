from classify import _is_borderline, resolve_votes
from schema import Classification, IntentType


def _c(intent, conf, quote="we are comparing tools for our team"):
    return Classification(intent_type=intent, need="n", evidence_quote=quote, confidence=conf, suggested_angle="a")


def test_borderline_flags_shortquote_and_lowconf():
    assert _is_borderline(_c(IntentType.active_need, 0.9, quote="Website"))   # one-word quote
    assert _is_borderline(_c(IntentType.evaluating, 0.7))                     # low-ish confidence
    assert not _is_borderline(_c(IntentType.active_need, 0.95))               # confident + long quote
    assert not _is_borderline(_c(IntentType.noise, 0.9, quote="lol"))         # not surface-eligible


def test_majority_keeps_intent_but_scales_confidence():
    votes = [_c(IntentType.active_need, 0.9, "Website"), _c(IntentType.active_need, 0.9, "Website"), _c(IntentType.noise, 0.9, "Website")]
    out = resolve_votes(votes)
    assert out.intent_type == IntentType.active_need
    assert out.confidence == round(0.9 * (2 / 3), 2)  # split vote -> below 0.6 -> will route to review


def test_no_majority_breaks_conservative():
    votes = [_c(IntentType.active_need, 0.9), _c(IntentType.noise, 0.9), _c(IntentType.curious, 0.9)]
    assert resolve_votes(votes).intent_type == IntentType.noise


def test_unanimous_keeps_full_confidence():
    votes = [_c(IntentType.active_need, 0.85)] * 3
    out = resolve_votes(votes)
    assert out.intent_type == IntentType.active_need and out.confidence == 0.85
