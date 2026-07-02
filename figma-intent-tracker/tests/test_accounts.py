from accounts import match_account_demo, route
from schema import IntentType, PlanTier, SignalType


def test_match_hits_fixture():
    a = match_account_demo("Acme")
    assert a.matched and a.is_customer and a.plan == PlanTier.enterprise
    assert a.account_owner  # an AE is assigned


def test_match_normalizes_legal_suffix():
    assert match_account_demo("Acme Inc.").matched
    assert match_account_demo("northwind co").matched


def test_match_miss():
    assert not match_account_demo("Totally Unknown Co").matched


def test_enterprise_customer_with_intent_is_churn_risk_to_ae():
    a = match_account_demo("Acme")
    r = route(IntentType.active_need, a, "Acme")
    assert r.signal_type == SignalType.churn_risk
    assert r.priority == 0
    assert "AE" in r.recipient


def test_free_customer_is_upsell():
    a = match_account_demo("Brightloom")
    r = route(IntentType.evaluating, a, "Brightloom")
    assert r.signal_type == SignalType.upsell
    assert r.priority == 1


def test_known_non_customer_is_net_new():
    a = match_account_demo("Vaultline")
    r = route(IntentType.curious, a, "Vaultline")
    assert r.signal_type == SignalType.net_new


def test_unknown_company_is_net_new_to_ae():
    # Figma has no SDR function: net-new routes to a territory AE, never an SDR.
    a = match_account_demo("Avery Labs")
    r = route(IntentType.active_need, a, "Avery Labs")
    assert r.signal_type == SignalType.net_new
    assert "AE" in r.recipient
    assert "SDR" not in r.recipient


def test_no_company_routes_to_enrich():
    r = route(IntentType.active_need, None, None)
    assert r.signal_type == SignalType.enrich
