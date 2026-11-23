import pytest

from claimcheck import paths


def test_project_root_holds_the_spaced_folders():
    assert paths.RAW_DIR.name == "1. RAW DATA"
    assert paths.RAW_DIR.is_dir()
    assert paths.INSTRUCTIONS_DIR.is_dir()
    assert (paths.PROJECT_ROOT / "pyproject.toml").is_file()


@pytest.mark.parametrize(
    "path",
    [
        paths.CLAIMS_HISTORY_CSV,
        paths.CLAIMS_TO_CHECK_CSV,
        paths.AUTHORIZATIONS_CSV,
        paths.EVV_VISITS_CSV,
    ],
)
def test_raw_inputs_exist(path):
    assert path.is_file()


def test_outputs_are_inside_the_project_outputs_folder():
    assert paths.output_path("x.csv") == paths.PROJECT_ROOT / "outputs" / "x.csv"


def test_missing_root_raises(tmp_path, monkeypatch):
    monkeypatch.delenv(paths.ROOT_ENV_VAR, raising=False)
    with pytest.raises(FileNotFoundError):
        paths.find_project_root(tmp_path)


def test_bad_root_override_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    with pytest.raises(FileNotFoundError):
        paths.find_project_root()
