from datetime import date

import pandas as pd
import pytest

from claimcheck import split as sp
from claimcheck.data import DataError, load_claims


@pytest.fixture(scope="module")
def history():
    return load_claims("history")


@pytest.fixture(scope="module")
def made(history):
    return sp.make_split(history)


def test_every_claim_is_on_exactly_one_side(history, made):
    assert made["claim_id"].is_unique
    assert set(made["claim_id"]) == set(history["claim_id"])
    assert set(made["split"]) == {"dev", "test"}
    dev = set(made.loc[made["split"] == "dev", "claim_id"])
    test = set(made.loc[made["split"] == "test", "claim_id"])
    assert not dev & test


def test_sizes_are_about_70_30(made):
    share = (made["split"] == "test").mean()
    assert abs(share - 0.30) < 0.005
    assert len(made) == 3830


def test_stratum_shares_within_two_points(history, made):
    df = history.merge(made, on="claim_id")
    df["stratum"] = sp.stratum(df)
    dev = df.loc[df["split"] == "dev", "stratum"].value_counts(normalize=True)
    test = df.loc[df["split"] == "test", "stratum"].value_counts(normalize=True)
    assert set(dev.index) == set(test.index), "a stratum is missing from one side"
    assert (dev - test).abs().max() < 0.02


def test_split_is_deterministic_and_ignores_row_order(history, made):
    shuffled = history.sample(frac=1, random_state=1)
    pd.testing.assert_frame_equal(sp.make_split(shuffled), made)


def test_file_is_reused_on_rerun(history, tmp_path):
    path = tmp_path / "split.csv"
    first = sp.load_or_create_split(history, path=path)
    # Tamper with the saved file: a rerun must return the file, not a fresh split.
    edited = first.copy()
    edited.loc[0, "split"] = "test" if edited.loc[0, "split"] == "dev" else "dev"
    edited.to_csv(path, index=False)
    second = sp.load_or_create_split(history, path=path)
    assert second.loc[0, "split"] == edited.loc[0, "split"]
    forced = sp.load_or_create_split(history, path=path, force=True)
    assert forced.loc[0, "split"] == first.loc[0, "split"]


def test_stale_split_file_raises(history, tmp_path):
    path = tmp_path / "split.csv"
    sp.make_split(history).iloc[:-1].to_csv(path, index=False)
    with pytest.raises(DataError, match="does not match"):
        sp.load_or_create_split(history, path=path)


def test_time_split_cutoff():
    df = pd.DataFrame({"submitted_date": [date(2026, 10, 14), date(2026, 10, 15), date(2027, 1, 1)]})
    assert list(sp.time_split(df)) == ["dev", "test", "test"]


def test_saved_split_matches_the_seeded_split(history, made):
    """outputs/split.csv is the locked split: same as seed 42 on today's history."""
    saved = sp.load_or_create_split(history).sort_values("claim_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(saved, made)
