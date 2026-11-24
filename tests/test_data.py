from datetime import date, datetime

import pandas as pd
import pytest

from claimcheck import data
from claimcheck.data import DataError


def raw_claim(**overrides) -> dict:
    """One raw history row, as text cells, the way read_raw_csv returns it."""
    row = {
        "claim_id": "C1", "agency_id": "AG001", "payer": "PY01", "patient_id": "PT0001",
        "service_code": "T1019", "date_of_service": "2026-06-09",
        "submitted_date": "2026-06-20", "units": "8", "auth_id": "AUTH1",
        "modifier": "", "frequency_code": "1", "original_claim_id": "",
        "billed_amount": "48.8", "status": "paid", "paid_amount": "48.8",
        "denial_code": "", "remark": "",
    }
    row.update(overrides)
    return row


def raw_frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), dtype=str)


# --- payer mapping -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("PY01", "PY01"), ("NORTHWIND HP", "PY01"), ("Northwind Health Plan", "PY01"),
        ("PY02", "PY02"), ("Harbor Medicaid Plan", "PY02"), ("Harbor Medicaid", "PY02"),
        ("PY03", "PY03"), ("SUMMIT CARE", "PY03"), ("Summit Care Partners", "PY03"),
        (" PY02 ", "PY02"),
    ],
)
def test_payer_mapping(raw, expected):
    assert data.normalise_payer(raw) == expected


@pytest.mark.parametrize("raw", ["Acme Health", "", "PY04", "northwind hp"])
def test_unknown_payer_raises(raw):
    with pytest.raises(DataError, match="Unknown payer"):
        data.normalise_payer(raw)


def test_unknown_payer_in_a_frame_names_the_column():
    with pytest.raises(DataError, match="'payer'"):
        data.clean_claims(raw_frame(raw_claim(payer="Acme Health")), "history")


# --- codes and modifiers -----------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [("U1", "U1"), (" U1", "U1"), ("U1 ", "U1"), ("u1", "U1"), (" u3 ", "U3"),
     ("T1019 ", "T1019"), ("", None), ("   ", None), (None, None), (float("nan"), None)],
)
def test_code_normalisation(raw, expected):
    assert data.normalise_code(raw) == expected


def test_empty_modifier_and_auth_stay_none_in_the_frame():
    df, _ = data.clean_claims(raw_frame(raw_claim(modifier=" ", auth_id="")), "history")
    assert df.loc[0, "modifier"] is None
    assert df.loc[0, "auth_id"] is None
    assert df.loc[0, "original_claim_id"] is None


# --- dates -------------------------------------------------------------------

def test_both_date_formats():
    assert data.parse_date("2026-06-09") == date(2026, 6, 9)
    assert data.parse_date("09/13/2026") == date(2026, 9, 13)
    # US format is month/day/year, also when the day could be a month.
    assert data.parse_date("07/09/2026") == date(2026, 7, 9)


@pytest.mark.parametrize("raw", ["13/09/2026", "2026-13-01", "9 June 2026", "", "2026/06/09"])
def test_bad_date_raises(raw):
    with pytest.raises(DataError, match="Unparseable date"):
        data.parse_date(raw)


def test_dates_are_plain_date_objects_in_the_frame():
    df, report = data.clean_claims(
        raw_frame(raw_claim(date_of_service="06/09/2026", submitted_date="2026-06-20")), "history"
    )
    assert df.loc[0, "date_of_service"] == date(2026, 6, 9)
    assert type(df.loc[0, "submitted_date"]) is date
    assert report["us_format_dates"] == {"date_of_service": 1, "submitted_date": 0}


def test_bad_date_in_a_frame_raises_and_drops_nothing():
    with pytest.raises(DataError, match="'date_of_service'"):
        data.clean_claims(raw_frame(raw_claim(), raw_claim(claim_id="C2", date_of_service="soon")), "history")


# --- duplicates and validation -----------------------------------------------

def test_exact_duplicate_rows_are_dropped_and_counted():
    df, report = data.clean_claims(raw_frame(raw_claim(), raw_claim(), raw_claim(claim_id="C2")), "history")
    assert list(df["claim_id"]) == ["C1", "C2"]
    assert report["rows_in"] == 3 and report["rows_out"] == 2
    assert report["exact_duplicate_rows_dropped"] == 1


def test_same_claim_id_with_different_content_raises():
    with pytest.raises(DataError, match="not unique"):
        data.clean_claims(raw_frame(raw_claim(), raw_claim(units="9")), "history")


@pytest.mark.parametrize(
    "overrides",
    [
        {"units": "eight"}, {"units": "8.5"}, {"units": "0"}, {"frequency_code": "3"},
        {"status": "pending"}, {"status": "paid", "denial_code": "D01"},
        {"status": "denied", "denial_code": ""}, {"patient_id": " "},
    ],
)
def test_invalid_values_raise(overrides):
    with pytest.raises(DataError):
        data.clean_claims(raw_frame(raw_claim(**overrides)), "history")


def test_missing_column_raises():
    with pytest.raises(DataError, match="missing column"):
        data.clean_claims(raw_frame(raw_claim()).drop(columns=["units"]), "history")


def test_remark_is_never_returned_by_clean_claims():
    df, _ = data.clean_claims(
        raw_frame(raw_claim(status="denied", denial_code="d01", paid_amount="0", remark="EVV verification not found")),
        "history",
    )
    assert "remark" not in df.columns
    assert df.loc[0, "denial_code"] == "D01"


def test_to_check_has_no_outcome_columns():
    row = {k: v for k, v in raw_claim(frequency_code="7", original_claim_id="C0").items()
           if k not in data.OUTCOME_COLUMNS}
    df, report = data.clean_claims(raw_frame(row), "to_check")
    assert not set(data.OUTCOME_COLUMNS) & set(df.columns)
    assert df.loc[0, "source"] == "to_check"
    assert report["frequency_7"] == 1


# --- EVV and authorizations --------------------------------------------------

def test_evv_timestamps_and_status():
    raw = raw_frame({
        "visit_id": "V1", "caregiver_id": "CG1", "patient_id": "PT1", "service_code": "t1019 ",
        "clock_in": "2026-06-09 22:00", "clock_out": "2026-06-10 02:00",
        "verification_status": "verified",
    })
    df, report = data.clean_evv(raw)
    assert df.loc[0, "clock_in"] == datetime(2026, 6, 9, 22, 0)
    assert df.loc[0, "service_code"] == "T1019"
    assert report["crosses_midnight"] == 1


@pytest.mark.parametrize(
    "overrides",
    [{"verification_status": "approved"}, {"clock_out": "2026-06-09 08:00"}, {"clock_in": "09/06/2026 08:00"}],
)
def test_bad_evv_raises(overrides):
    row = {
        "visit_id": "V1", "caregiver_id": "CG1", "patient_id": "PT1", "service_code": "T1019",
        "clock_in": "2026-06-09 08:00", "clock_out": "2026-06-09 10:00",
        "verification_status": "verified",
    }
    row.update(overrides)
    with pytest.raises(DataError):
        data.clean_evv(raw_frame(row))


def test_auth_cleaning_and_bad_dates():
    row = {
        "auth_id": "AUTH1", "patient_id": "PT1", "payer_id": "PY03", "service_code": "T1005",
        "start_date": "2026-06-01", "end_date": "2026-08-31", "units_authorized": "216",
    }
    df, _ = data.clean_auths(raw_frame(row))
    assert df.loc[0, "start_date"] == date(2026, 6, 1)
    assert df.loc[0, "units_authorized"] == 216
    with pytest.raises(DataError, match="end_date before start_date"):
        data.clean_auths(raw_frame({**row, "end_date": "2026-05-31"}))


# --- the real files ----------------------------------------------------------

@pytest.fixture(scope="module")
def history():
    return data.load_claims("history")


@pytest.fixture(scope="module")
def to_check():
    return data.load_claims("to_check")


def test_history_3862_rows_become_3830(history):
    report = history.attrs["cleaning_report"]
    assert report["rows_in"] == 3862
    assert report["exact_duplicate_rows_dropped"] == 32
    assert len(history) == 3830
    assert history["claim_id"].is_unique


def test_history_is_fully_normalised(history):
    assert set(history["payer_id"]) == {"PY01", "PY02", "PY03"}
    assert set(history["service_code"]) == {"T1019", "T1005", "S5125"}
    assert set(history["modifier"].dropna()) == {"U1", "U2", "U3"}
    assert all(type(d) is date for d in history["date_of_service"])
    assert all(type(d) is date for d in history["submitted_date"])
    assert "remark" not in history.columns


def test_to_check_546_rows_with_14_corrected_claims(to_check):
    assert len(to_check) == 546
    assert to_check["claim_id"].is_unique
    assert (to_check["frequency_code"] == 7).sum() == 14
    assert set(to_check["payer_id"]) == {"PY01", "PY02", "PY03"}
    assert not {"status", "denial_code", "remark"} & set(to_check.columns)


def test_no_claim_id_is_in_both_files(history, to_check):
    assert not set(history["claim_id"]) & set(to_check["claim_id"])


def test_evv_and_auth_row_counts():
    assert len(data.load_evv()) == 5076
    assert len(data.load_auths()) == 780


def test_remarks_load_separately_and_align_with_history(history):
    remarks = data.load_remarks()
    assert list(remarks.columns) == ["claim_id", "remark"]
    assert set(remarks["claim_id"]) == set(history["claim_id"])
