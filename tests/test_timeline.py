"""Rules that depend on earlier claims: duplicates, authorization balance, daily maximum."""
from datetime import date, datetime, timedelta

import pandas as pd

from claimcheck import predict, rules
from claimcheck.config import default_config
from claimcheck.rules import ClaimContext
from claimcheck.timeline import TimelineState

CFG = default_config()
DOS = date(2026, 9, 9)


def claim(claim_id="C1", **overrides) -> dict:
    base = {
        "claim_id": claim_id, "agency_id": "AG001", "payer_id": "PY02", "patient_id": "PT1",
        "service_code": "T1005", "date_of_service": DOS, "submitted_date": DOS + timedelta(days=5),
        "units": 8, "auth_id": "AUTH1", "modifier": None, "frequency_code": 1,
        "original_claim_id": None, "billed_amount": 40.0, "source": "to_check",
    }
    base.update(overrides)
    return base


AUTH = {"auth_id": "AUTH1", "patient_id": "PT1", "payer_id": "PY02", "service_code": "T1005",
        "start_date": date(2026, 9, 1), "end_date": date(2026, 11, 30), "units_authorized": 20}


def state() -> TimelineState:
    return TimelineState(duplicate_key=CFG["global"]["duplicate_key"])


# --- duplicates (D05) ---------------------------------------------------------

def test_second_claim_with_same_key_is_a_duplicate_even_if_the_first_was_denied():
    s = state()
    s.record(claim("C1"), paid=False)
    second = claim("C2")
    ctx = ClaimContext(dup_of_claim_id=s.earlier_claim_with_same_key(second))
    hit = rules.check_duplicate(second, ctx, CFG)
    assert hit.denial_code == "D05" and hit.details["dup_of_claim_id"] == "C1"


def test_corrected_claim_is_not_a_duplicate():
    s = state()
    s.record(claim("C1"), paid=False)
    corrected = claim("C2", frequency_code=7, original_claim_id="C1")
    ctx = ClaimContext(dup_of_claim_id=s.earlier_claim_with_same_key(corrected))
    assert ctx.dup_of_claim_id == "C1"
    assert rules.check_duplicate(corrected, ctx, CFG) is None


def test_different_service_date_patient_or_payer_is_not_a_duplicate():
    s = state()
    s.record(claim("C1"), paid=True)
    for other in (claim("C2", service_code="S5125"), claim("C2", date_of_service=DOS + timedelta(days=1)),
                  claim("C2", patient_id="PT2"), claim("C2", payer_id="PY03")):
        assert s.earlier_claim_with_same_key(other) is None


# --- authorization balance (D02) ----------------------------------------------

def test_only_paid_claims_draw_down_the_authorization():
    s = state()
    s.record(claim("C1", units=8), paid=True)
    s.record(claim("C2", units=8, date_of_service=DOS + timedelta(days=1)), paid=False)
    assert s.auth_remaining(AUTH) == 12
    assert s.auth_remaining(None) is None


def test_units_equal_to_the_balance_pass_and_one_more_is_denied():
    ctx = ClaimContext(auth=AUTH, auth_remaining_before=12)
    assert rules.check_auth_units(claim(units=12), ctx, CFG) is None
    hit = rules.check_auth_units(claim(units=13), ctx, CFG)
    assert hit.denial_code == "D02" and "12 units" in hit.fix


def test_exhausted_authorization_asks_for_a_new_one():
    hit = rules.check_auth_units(claim(units=4), ClaimContext(auth=AUTH, auth_remaining_before=0), CFG)
    assert hit.denial_code == "D02" and "used up" in hit.fix


def test_balance_is_not_checked_on_an_authorization_that_does_not_fit():
    wrong = dict(AUTH, service_code="T1019")
    assert rules.check_auth_units(claim(units=99), ClaimContext(auth=wrong, auth_remaining_before=0), CFG) is None


# --- daily maximum (D06) ------------------------------------------------------

def test_daily_total_of_exactly_32_passes_and_33_is_denied():
    ctx = ClaimContext(daily_paid_before=24)
    assert rules.check_daily_max(claim(units=8), ctx, CFG) is None
    hit = rules.check_daily_max(claim(units=9), ctx, CFG)
    assert hit.denial_code == "D06" and hit.details == {"daily_paid_before": 24, "limit": 32}


def test_daily_maximum_counts_paid_units_across_services_for_the_same_day():
    s = state()
    s.record(claim("C1", units=20, service_code="T1019"), paid=True)
    s.record(claim("C2", units=10, service_code="S5125"), paid=False)   # denied: not counted
    s.record(claim("C3", units=10, date_of_service=DOS + timedelta(days=1)), paid=True)  # other day
    assert s.daily_paid_units(claim("C4")) == 20


def test_daily_maximum_applies_only_to_harbor():
    assert rules.check_daily_max(claim(payer_id="PY01", units=40), ClaimContext(daily_paid_before=30), CFG) is None


# --- the walk through the timeline ----------------------------------------------

def _frames():
    rows = [
        claim("C1", units=16, submitted_date=date(2026, 9, 10)),
        claim("C2", units=16, service_code="S5125", auth_id="AUTH2", submitted_date=date(2026, 9, 11)),
        claim("C3", units=4, service_code="T1019", auth_id="AUTH3", modifier="U2", submitted_date=date(2026, 9, 12)),
        claim("C4", units=16, submitted_date=date(2026, 9, 13)),
    ]
    auths = pd.DataFrame([
        dict(AUTH, units_authorized=100),
        dict(AUTH, auth_id="AUTH2", service_code="S5125", units_authorized=100),
        dict(AUTH, auth_id="AUTH3", service_code="T1019", units_authorized=100),
    ])
    evv = pd.DataFrame([
        {"visit_id": f"V{i}", "patient_id": "PT1", "service_code": service,
         "clock_in": datetime(2026, 9, 9, 8, 0), "clock_out": datetime(2026, 9, 9, 12, 0),
         "verification_status": "verified"}
        for i, service in enumerate(["T1005", "S5125", "T1019"])
    ])
    return pd.DataFrame(rows), evv, auths


def test_walk_applies_daily_max_then_duplicate_in_submission_order():
    claims, evv, auths = _frames()
    out = predict.predict_claims(claims, evv, auths).set_index("claim_id")
    assert out.loc["C1", "status"] == "paid" and out.loc["C2", "status"] == "paid"
    assert out.loc["C3", "denial_code"] == "D06"            # 32 already paid that day
    assert out.loc["C3", "daily_paid_before"] == 32
    assert "D05" in out.loc["C4", "all_hits"]               # same key as C1
    assert out.loc["C4", "dup_of_claim_id"] == "C1"


def test_known_outcomes_drive_the_state_instead_of_predictions():
    claims, evv, auths = _frames()
    # The payer really denied C1 and C2, so nothing was paid that day: C3 is now within the limit.
    out = predict.predict_claims(claims, evv, auths, known_status={"C1": "denied", "C2": "denied"})
    assert out.set_index("claim_id").loc["C3", "status"] == "paid"


def test_claim_close_to_a_limit_is_sent_to_review():
    claims, evv, auths = _frames()
    auths.loc[auths["auth_id"] == "AUTH1", "units_authorized"] = 17   # 1 unit left after C1
    out = predict.predict_claims(claims.iloc[:1], evv, auths).iloc[0]
    assert out["status"] == "paid" and out["needs_review"] and out["action"] == "review"


def test_single_large_claim_with_nothing_else_that_day_is_not_sent_to_review():
    claims, evv, auths = _frames()
    big = claims.iloc[:1].assign(units=16)
    evv = evv.assign(clock_out=datetime(2026, 9, 9, 16, 0))   # 8 hours = 32 units of evidence
    out = predict.predict_claims(big.assign(units=32), evv, auths).iloc[0]
    assert out["status"] == "paid" and not out["needs_review"] and out["action"] == "submit"
