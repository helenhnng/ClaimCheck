"""The demo screen: upload a claims file, results are computed on the spot (run headlessly)."""
import pytest

from claimcheck import paths

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(paths.PROJECT_ROOT / "app" / "streamlit_app.py")
HEADER = ("claim_id,agency_id,payer,patient_id,service_code,date_of_service,submitted_date,"
          "units,auth_id,modifier,frequency_code,original_claim_id,billed_amount")


def fresh(file: tuple[str, bytes] | None = None) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=120)
    if file is not None:
        app.session_state["claims_file"] = file   # stands in for clicking "Browse"
    return app.run()


@pytest.fixture(scope="module")
def checked():
    return fresh(("claims_to_check.csv", paths.CLAIMS_TO_CHECK_CSV.read_bytes()))


def test_landing_page_asks_for_a_file_and_shows_no_results():
    app = fresh()
    assert not app.exception
    assert len(app.file_uploader) == 1
    assert not app.metric and not app.selectbox      # nothing pre-loaded
    assert "Upload a CSV" in app.info[0].value


def test_uploaded_file_is_checked_on_the_spot(checked):
    assert not checked.exception
    metrics = {m.label: int(m.value) for m in checked.metric}
    assert metrics["Claims checked"] == 546
    assert sum(v for k, v in metrics.items() if k != "Claims checked") == 546
    assert "Checked **546 claims**" in checked.success[0].value
    assert len(checked.selectbox[0].options) == 546


def test_filter_by_code_shows_rule_source_and_fix(checked):
    checked.sidebar.multiselect[2].set_value(["D04"]).run()
    assert not checked.exception
    text = " ".join(m.value for m in checked.markdown)
    assert "Rule broken:" in text and "Source:" in text and "Suggested fix:" in text
    checked.sidebar.multiselect[2].set_value([]).run()


def test_hold_claims_tell_the_biller_to_wait(checked):
    checked.sidebar.multiselect[1].set_value(["hold"]).run()
    assert not checked.exception
    assert "Hold" in checked.warning[0].value
    checked.sidebar.multiselect[1].set_value([]).run()


def test_a_small_new_file_gives_its_own_result():
    row = "X000001,AG001,Harbor Medicaid,PT0075,T1019,2026-09-05,09/08/2026,8,AUTH10948,U2,1,,48.8"
    app = fresh(("mine.csv", (HEADER + "\n" + row + "\n").encode()))
    assert not app.exception
    assert {m.label: m.value for m in app.metric}["Claims checked"] == "1"


@pytest.mark.parametrize(
    "body, expected",
    [
        ("X1,AG001,Acme Health,PT0075,T1019,2026-09-05,2026-09-08,8,AUTH10948,U2,1,,48.8", "Acme Health"),
        ("X1,AG001,PY02,PT0075,T1019,next week,2026-09-08,8,AUTH10948,U2,1,,48.8", "date_of_service"),
        ("C000007,AG001,PY02,PT0075,T1019,2026-09-05,2026-09-08,8,AUTH10948,U2,1,,48.8", "already in the adjudicated history"),
    ],
)
def test_a_bad_file_is_refused_with_the_reason(body, expected):
    app = fresh(("bad.csv", (HEADER + "\n" + body + "\n").encode()))
    assert not app.exception
    assert expected in app.error[0].value
    assert not app.metric


def test_a_file_with_missing_columns_is_refused():
    app = fresh(("bad.csv", b"claim_id,units\nX1,8\n"))
    assert not app.exception and "missing column" in app.error[0].value
