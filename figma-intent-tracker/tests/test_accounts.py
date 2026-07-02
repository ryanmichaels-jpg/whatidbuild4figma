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


# --- Change 3: intent x product-signal intercept ---

def test_intercept_escalates_active_need_when_seats_growing():
    # Glasshouse: pro customer, +5% seats/90d -> base upsell P1 escalates to P0
    a = match_account_demo("Glasshouse")
    assert a.product_signals and a.product_signals.seat_growth_90d_pct > 0
    r = route(IntentType.active_need, a, "Glasshouse")
    assert r.priority == 0
    assert "intercept" in r.rationale and "expansion-ready" in r.rationale


def test_intercept_cools_curious_heavy_user_to_nurture():
    # Acme: enterprise, 1200 seats, active 1 day ago -> curious becomes nurture (P3)
    a = match_account_demo("Acme")
    r = route(IntentType.curious, a, "Acme")
    assert r.priority == 3
    assert "nurture" in r.rationale


def test_why_now_line_is_populated_from_the_join():
    a = match_account_demo("Northwind")
    r = route(IntentType.active_need, a, "Northwind")
    assert r.why_now and "seats" in r.why_now
    # net-new (no footprint) still gets a why_now
    r2 = route(IntentType.active_need, match_account_demo("Avery Labs"), "Avery Labs")
    assert r2.why_now and "net-new" in r2.why_now
