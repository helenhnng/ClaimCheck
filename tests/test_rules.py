"""Stateless rules, each tested with a hand-built claim (BUILD_SPEC 6.6 boundaries)."""
import copy
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from claimcheck import rules
from claimcheck.config import ConfigError, default_config, filing_rule, load_config, modifier_rule
from claimcheck.evv import EvvDay, build_evv_index, round_units, supported_units
from claimcheck.rules import ClaimContext

CFG = default_config()
DOS = date(2026, 9, 9)  # a Wednesday


def claim(**overrides) -> dict:
    base = {
        "claim_id": "C1", "agency_id": "AG001", "payer_id": "PY01", "patient_id": "PT1",
        "service_code": "T1005", "date_of_service": DOS, "submitted_date": DOS + timedelta(days=5),
        "units": 8, "auth_id": "AUTH1", "modifier": None, "frequency_code": 1,
        "original_claim_id": None, "billed_amount": 40.0, "source": "to_check",
    }
    base.update(overrides)
    return base


def auth(**overrides) -> dict:
    base = {
        "auth_id": "AUTH1", "patient_id": "PT1", "payer_id": "PY01", "service_code": "T1005",
        "start_date": date(2026, 9, 1), "end_date": date(2026, 11, 30), "units_authorized": 100,
    }
    base.update(overrides)
    return base


def ctx(minutes=(120,), **overrides) -> ClaimContext:
    day = EvvDay(verified_minutes=list(minutes), verified_visit_ids=[f"V{i}" for i in range(len(minutes))])
    base = {"evv": day, "auth": auth()}
    base.update(overrides)
    return ClaimContext(**base)


def codes(c, x, cfg=CFG) -> list[str]:
    return [h.denial_code for h in rules.evaluate_rules(c, x, cfg)]


def test_clean_claim_breaks_no_rule():
    assert codes(claim(), ctx()) == []


def test_every_hit_carries_the_required_fields():
    c = claim(auth_id=None, units=99, submitted_date=DOS + timedelta(days=200))
    hits = rules.evaluate_rules(c, ctx(auth=None), CFG)
    assert {h.denial_code for h in hits} == {"D07", "D03", "D09"}
    for hit in hits:
        assert hit.rule_id and hit.message and hit.citation and hit.fix


# --- D07 / D08 authorization -------------------------------------------------

def test_blank_auth_is_d07_not_d08():
    hit = rules.check_auth_missing(claim(auth_id=None), ctx(auth=None, candidate_auths=[auth()]), CFG)
    assert hit.denial_code == "D07" and "AUTH1" in hit.fix
    assert rules.check_auth_invalid(claim(auth_id=None), ctx(auth=None), CFG) is None


@pytest.mark.parametrize(
    "auth_overrides",
    [{"patient_id": "PT2"}, {"service_code": "T1019"}, {"payer_id": "PY02"},
     {"start_date": date(2026, 6, 1), "end_date": date(2026, 8, 31)}],
)
def test_auth_mismatch_is_d08(auth_overrides):
    hit = rules.check_auth_invalid(claim(), ctx(auth=auth(**auth_overrides)), CFG)
    assert hit.denial_code == "D08"


def test_auth_not_on_file_is_d08():
    assert rules.check_auth_invalid(claim(), ctx(auth=None), CFG).denial_code == "D08"


@pytest.mark.parametrize("dos", [date(2026, 9, 1), date(2026, 11, 30)])
def test_auth_window_is_inclusive(dos):
    c = claim(date_of_service=dos, submitted_date=dos + timedelta(days=1))
    assert rules.check_auth_invalid(c, ctx(), CFG) is None


# --- D03 timely filing -------------------------------------------------------

@pytest.mark.parametrize(
    "payer, dos, limit",
    [
        ("PY01", date(2026, 7, 31), 30),   # last day of the 30-day rule
        ("PY01", date(2026, 8, 1), 45),    # first day of the 45-day rule (Bulletin 2026-07)
        ("PY03", date(2026, 9, 9), 60),
    ],
)
def test_filing_exactly_at_the_limit_and_one_day_over(payer, dos, limit):
    at_limit = claim(payer_id=payer, date_of_service=dos, submitted_date=dos + timedelta(days=limit))
    over = claim(payer_id=payer, date_of_service=dos, submitted_date=dos + timedelta(days=limit + 1))
    assert rules.check_timely_filing(at_limit, ctx(), CFG) is None
    hit = rules.check_timely_filing(over, ctx(), CFG)
    assert hit.denial_code == "D03" and hit.details == {"days": limit + 1, "limit": limit}


def test_filing_boundary_switch():
    cfg = copy.deepcopy(CFG)
    cfg["global"]["filing_boundary"] = "ge"
    at_limit = claim(payer_id="PY03", submitted_date=DOS + timedelta(days=60))
    assert rules.check_timely_filing(at_limit, ctx(), cfg).denial_code == "D03"


def test_py02_has_no_filing_limit():
    late = claim(payer_id="PY02", submitted_date=DOS + timedelta(days=300))
    assert rules.check_timely_filing(late, ctx(), CFG) is None
    assert filing_rule(CFG, "PY02", DOS) is None


# --- D01 / D09 EVV -----------------------------------------------------------

def test_no_verified_evv_is_d01_and_skips_d09():
    assert codes(claim(units=99), ctx(minutes=())) == ["D01"]


def test_pending_evv_gives_hold_advice():
    day = EvvDay(pending_visit_ids=["V9"])
    hit = rules.check_evv_missing(claim(), ctx(evv=day), CFG)
    assert hit.denial_code == "D01" and hit.fix.startswith("Hold") and "V9" in hit.fix


def test_rejected_evv_is_d01():
    hit = rules.check_evv_missing(claim(), ctx(evv=EvvDay(rejected_visit_ids=["V8"])), CFG)
    assert hit.denial_code == "D01" and "rejected" in hit.message


@pytest.mark.parametrize(
    "minutes, method, expected",
    [(127, "eight_minute_rule", 8), (128, "eight_minute_rule", 9),   # remainder 7 vs 8
     (127, "floor", 8), (134, "floor", 8), (135, "floor", 9), (0, "floor", 0)],
)
def test_rounding(minutes, method, expected):
    assert round_units(minutes, method) == expected


def test_py01_remainder_seven_vs_eight_minutes():
    nine_units = claim(payer_id="PY01", units=9)
    assert rules.check_evv_units(nine_units, ctx(minutes=(127,)), CFG).denial_code == "D09"
    assert rules.check_evv_units(nine_units, ctx(minutes=(128,)), CFG) is None


def test_floor_payer_gets_no_extra_unit():
    hit = rules.check_evv_units(claim(payer_id="PY03", units=9), ctx(minutes=(128,)), CFG)
    assert hit.denial_code == "D09" and hit.details["supported_units"] == 8


def test_units_equal_to_evv_units_pass():
    assert rules.check_evv_units(claim(units=8), ctx(minutes=(120,)), CFG) is None


def test_two_same_day_visits_are_summed_before_rounding():
    day = EvvDay(verified_minutes=[52, 53])  # 105 min = 7 units; rounded separately = 3 + 3
    py03 = CFG["payers"]["PY03"]
    assert supported_units(day, py03, CFG["global"]) == 7
    alt = dict(CFG["global"], evv_aggregation="round_then_sum")
    assert supported_units(day, py03, alt) == 6


def test_overnight_visit_is_dated_to_clock_in_and_unverified_is_ignored():
    evv = pd.DataFrame([
        {"visit_id": "V1", "patient_id": "PT1", "service_code": "T1005",
         "clock_in": datetime(2026, 9, 9, 22, 0), "clock_out": datetime(2026, 9, 10, 2, 0),
         "verification_status": "verified"},
        {"visit_id": "V2", "patient_id": "PT1", "service_code": "T1005",
         "clock_in": datetime(2026, 9, 9, 8, 0), "clock_out": datetime(2026, 9, 9, 9, 0),
         "verification_status": "manual_edit_pending"},
    ])
    index = build_evv_index(evv, CFG["global"])
    assert ("PT1", "T1005", date(2026, 9, 10)) not in index
    day = index[("PT1", "T1005", date(2026, 9, 9))]
    assert day.verified_minutes == [240] and day.pending_visit_ids == ["V2"]


# --- D04 modifier ------------------------------------------------------------

SAT_BEFORE, SAT_AFTER = date(2026, 8, 29), date(2026, 9, 5)   # Saturdays either side of 1 Sep
MON_BEFORE, MON_AFTER = date(2026, 8, 31), date(2026, 9, 7)   # weekdays either side


def harbor(dos, modifier, service="T1019") -> dict:
    return claim(payer_id="PY02", service_code=service, date_of_service=dos,
                 submitted_date=dos + timedelta(days=3), modifier=modifier)


@pytest.mark.parametrize(
    "dos, modifier, denied",
    [
        (SAT_BEFORE, "U2", False), (SAT_BEFORE, "U3", True),   # weekend before the notice: U2
        (SAT_AFTER, "U3", False), (SAT_AFTER, "U2", True),     # weekend from 1 Sep: U3
        (date(2026, 9, 6), "U3", False),                       # Sunday
        (MON_BEFORE, "U2", False), (MON_AFTER, "U2", False), (MON_AFTER, "U3", True),
        (MON_AFTER, None, True), (MON_AFTER, "U1", True),
    ],
)
def test_harbor_t1019_modifier(dos, modifier, denied):
    hit = rules.check_modifier(harbor(dos, modifier), ctx(), CFG)
    assert (hit is not None) == denied
    if denied:
        assert hit.denial_code == "D04" and hit.details["required"] in hit.fix


def test_weekday_check_uses_the_calendar():
    assert SAT_BEFORE.weekday() == 5 and SAT_AFTER.weekday() == 5 and MON_BEFORE.weekday() == 0


def test_modifier_rule_only_applies_to_harbor_t1019():
    assert rules.check_modifier(harbor(SAT_AFTER, None, service="T1005"), ctx(), CFG) is None
    assert rules.check_modifier(claim(payer_id="PY01", service_code="T1019", modifier="U1"), ctx(), CFG) is None
    assert modifier_rule(CFG, "PY03", "T1019", DOS) is None


# --- precedence, config, leakage ---------------------------------------------

def test_precedence_picks_one_code():
    c = claim(auth_id=None, units=99, submitted_date=DOS + timedelta(days=200))
    hits = rules.evaluate_rules(c, ctx(auth=None), CFG)
    assert rules.pick_hit(hits, ["D07", "D03", "D09"]).denial_code == "D07"
    assert rules.pick_hit(hits, ["D09", "D03", "D07"]).denial_code == "D09"
    assert rules.pick_hit([], ["D07"]) is None
    with pytest.raises(ValueError):
        rules.pick_hit(hits, ["D07"])


def test_config_is_valid_and_bad_values_raise(tmp_path):
    assert set(CFG["payers"]) == {"PY01", "PY02", "PY03"}
    bad = copy.deepcopy(load_config())
    bad["payers"]["PY01"]["rounding"] = "nearest"
    from claimcheck.config import validate
    with pytest.raises(ConfigError):
        validate(bad)


class _Spy(dict):
    """A claim that records which fields the rules read."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read = set()

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)


def test_rules_never_read_remark_or_outcome_fields():
    spy = _Spy(claim(payer_id="PY02", service_code="T1019", units=99, modifier=None,
                     status="denied", denial_code="D04", remark="Invalid or missing modifier"))
    rules.evaluate_rules(spy, ctx(), CFG)
    assert spy.read, "the spy saw no reads"
    assert spy.read <= rules.ALLOWED_CLAIM_FIELDS
    assert not spy.read & {"remark", "status", "denial_code", "paid_amount"}


# --- PY03 contract amendment 3 (D10) and payer-specific code order ------------

@pytest.mark.parametrize(
    "dos, units, denied",
    [
        (date(2026, 6, 30), 18, False),   # before the amendment takes effect
        (date(2026, 7, 1), 18, True),     # first day: 18 units is 4.5 hours
        (date(2026, 7, 1), 16, False),    # whole hours
        (date(2026, 9, 9), 17, True),
    ],
)
def test_summit_whole_hours_rule(dos, units, denied):
    c = claim(payer_id="PY03", date_of_service=dos, submitted_date=dos + timedelta(days=3), units=units)
    hit = rules.check_contract(c, ctx(), CFG)
    assert (hit is not None) == denied
    if denied:
        assert hit.denial_code == "D10" and "inferred" in hit.citation


def test_whole_hours_rule_is_summit_only():
    for payer in ("PY01", "PY02"):
        assert rules.check_contract(claim(payer_id=payer, units=17), ctx(), CFG) is None


def test_code_order_differs_for_summit():
    from claimcheck.config import precedence_for
    default, summit = precedence_for(CFG, "PY01"), precedence_for(CFG, "PY03")
    assert precedence_for(CFG, "PY02") == default
    assert default[0] == summit[0] == "D01"
    assert default.index("D09") < default.index("D07")      # EVV units before authorization
    assert summit.index("D07") < summit.index("D09")        # Summit: authorization first
    assert summit.index("D10") < summit.index("D09")
    assert default[-1] == summit[-1] == "D03"


def test_missing_evv_outranks_late_filing_end_to_end():
    from claimcheck.config import precedence_for
    late_no_evv = claim(submitted_date=DOS + timedelta(days=200))
    hits = rules.evaluate_rules(late_no_evv, ctx(minutes=()), CFG)
    assert {h.denial_code for h in hits} == {"D01", "D03"}
    assert rules.pick_hit(hits, precedence_for(CFG, "PY01")).denial_code == "D01"
