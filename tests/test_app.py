"""The demo screen loads and its filters work (run headlessly, no browser)."""
import pytest

from claimcheck import paths

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(paths.PROJECT_ROOT / "app" / "streamlit_app.py")


@pytest.fixture(scope="module")
def app():
    if not (paths.OUTPUTS_DIR / "predictions_detailed.csv").is_file():
        pytest.skip("run `python -m claimcheck.predict` first")
    return AppTest.from_file(APP, default_timeout=60).run()


def test_screen_loads_with_all_claims(app):
    assert not app.exception
    metrics = {m.label: int(m.value) for m in app.metric}
    assert metrics["Claims checked"] == 546
    assert sum(v for k, v in metrics.items() if k != "Claims checked") == 546
    assert len(app.selectbox[0].options) == 546


def test_filter_by_code_shows_rule_source_and_fix(app):
    app.sidebar.multiselect[2].set_value(["D04"]).run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "Rule broken:" in text and "Source:" in text and "Suggested fix:" in text
    app.sidebar.multiselect[2].set_value([]).run()


def test_hold_claims_tell_the_biller_to_wait(app):
    app.sidebar.multiselect[1].set_value(["hold"]).run()
    assert not app.exception
    assert "Hold" in app.warning[0].value
    app.sidebar.multiselect[1].set_value([]).run()
