import pandas as pd
import pytest

from claimcheck import predict
from claimcheck.data import load_auths, load_claims, load_evv
from claimcheck.integrity import hash_raw_data
from claimcheck.rules import ALLOWED_CLAIM_FIELDS


@pytest.fixture(scope="module")
def to_check():
    return load_claims("to_check")


@pytest.fixture(scope="module")
def detailed(to_check):
    before = hash_raw_data()
    out = predict.predict_claims(to_check, load_evv(), load_auths())
    assert hash_raw_data() == before, "a prediction run changed the raw data"
    return out


def test_predictions_schema(to_check, detailed):
    pred = detailed[predict.PREDICTION_COLUMNS]
    predict.validate_predictions(pred, set(to_check["claim_id"]))
    assert len(pred) == 546
    assert set(pred["status"]) <= {"paid", "denied"}
    assert ((pred["status"] == "paid") == (pred["denial_code"] == "")).all()
    assert "D99" not in set(pred["denial_code"])


def test_detailed_columns_and_actions(detailed):
    assert list(detailed.columns) == predict.DETAIL_COLUMNS
    assert set(detailed["action"]) <= {"submit", "fix_then_submit", "hold", "review"}
    denied = detailed[detailed["status"] == "denied"]
    for column in ("rule_id", "message", "citation", "fix"):
        assert (denied[column].str.len() > 0).all(), f"a denied claim has no {column}"


def test_corrected_claims_go_to_review(to_check, detailed):
    freq7 = set(to_check.loc[to_check["frequency_code"] == 7, "claim_id"])
    rows = detailed[detailed["claim_id"].isin(freq7)]
    assert len(rows) == 14 and rows["needs_review"].all()
    assert set(rows["action"]) <= {"review", "hold"}


def test_hold_only_for_pending_evv(detailed):
    hold = detailed[detailed["action"] == "hold"]
    assert (hold["denial_code"] == "D01").all()
    assert hold["fix"].str.startswith("Hold").all()


def test_outcome_and_remark_columns_never_reach_the_rules():
    history = load_claims("history").head(50).copy()
    history["remark"] = "leak"
    records = predict.claim_records(history)
    assert all(set(r) <= ALLOWED_CLAIM_FIELDS for r in records)
    assert not {"remark", "status", "denial_code", "paid_amount"} & set(records[0])


def test_claims_are_walked_in_submission_order(to_check):
    records = predict.claim_records(to_check)
    keys = [(r["submitted_date"], r["claim_id"]) for r in records]
    assert keys == sorted(keys)


def test_bad_prediction_files_are_rejected():
    good = pd.DataFrame({"claim_id": ["C1"], "status": ["paid"], "denial_code": [""]})
    predict.validate_predictions(good, {"C1"})
    with pytest.raises(ValueError):
        predict.validate_predictions(good.assign(denial_code="D01"), {"C1"})
    with pytest.raises(ValueError):
        predict.validate_predictions(good, {"C1", "C2"})
