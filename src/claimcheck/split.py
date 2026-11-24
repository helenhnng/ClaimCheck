"""Dev/test split of the cleaned history (BUILD_SPEC 5.9).

70/30, stratified by payer and outcome code, seed 42. The split is written to
``outputs/split.csv`` once and then reused, so "test" always means the same
claims. All rule investigation uses ``dev`` only; test is scored once.

    python -m claimcheck.split [--force]
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from claimcheck import paths
from claimcheck.data import DataError, load_claims

TEST_SIZE = 0.30
RANDOM_STATE = 42
TIME_SPLIT_CUTOFF = date(2026, 10, 15)  # submitted on or after this date -> "test"
SPLIT_FILE = "split.csv"


def stratum(history: pd.DataFrame) -> pd.Series:
    """``payer_id + "_" + (denial_code or "PAID")``."""
    return history["payer_id"] + "_" + history["denial_code"].fillna("PAID")


def make_split(history: pd.DataFrame) -> pd.DataFrame:
    """Return ``claim_id, split`` (dev/test). Independent of the input row order."""
    ordered = history.sort_values("claim_id")
    strata = stratum(ordered)
    counts = strata.value_counts()
    if (counts < 2).any():
        raise DataError(f"Strata too small to split: {counts[counts < 2].to_dict()}")
    _, test_ids = train_test_split(
        ordered["claim_id"], test_size=TEST_SIZE, stratify=strata, random_state=RANDOM_STATE
    )
    test_ids = set(test_ids)
    return pd.DataFrame({
        "claim_id": ordered["claim_id"].to_numpy(),
        "split": ["test" if cid in test_ids else "dev" for cid in ordered["claim_id"]],
    })


def load_or_create_split(
    history: pd.DataFrame, path: Path | None = None, force: bool = False
) -> pd.DataFrame:
    """Load ``outputs/split.csv`` if it exists, else create and save it.

    A saved split that does not cover exactly the history claims raises; it is
    never regenerated silently (use ``force=True`` on purpose).
    """
    path = path or paths.output_path(SPLIT_FILE)
    if path.exists() and not force:
        split = pd.read_csv(path, dtype=str)
        if set(split.columns) != {"claim_id", "split"} or not set(split["split"]) <= {"dev", "test"}:
            raise DataError(f"{path} is not a valid split file")
        if split["claim_id"].duplicated().any() or set(split["claim_id"]) != set(history["claim_id"]):
            raise DataError(
                f"{path} does not match the history claims. Re-create it with --force "
                "only if the history really changed (this resets the test set)."
            )
        return split
    split = make_split(history)
    split.to_csv(path, index=False)
    return split


def time_split(history: pd.DataFrame) -> pd.Series:
    """Robustness check: ``dev`` if submitted before 2026-10-15, else ``test``."""
    return pd.Series(
        ["dev" if d < TIME_SPLIT_CUTOFF else "test" for d in history["submitted_date"]],
        index=history.index, name="time_split",
    )


def attach_split(history: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    """History with ``split`` and ``time_split`` columns added."""
    split = load_or_create_split(history, force=force)
    out = history.merge(split, on="claim_id", how="left", validate="one_to_one")
    out["time_split"] = time_split(out).to_numpy()
    return out


def payer_code_table(history_with_split: pd.DataFrame, side: str, column: str = "split") -> pd.DataFrame:
    """Claims by outcome code (rows) and payer (columns) for one side."""
    part = history_with_split[history_with_split[column] == side]
    return pd.crosstab(part["denial_code"].fillna("PAID"), part["payer_id"], margins=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="regenerate outputs/split.csv")
    args = parser.parse_args()
    df = attach_split(load_claims("history"), force=args.force)
    for column in ("split", "time_split"):
        print(f"\n== {column}: {df[column].value_counts().to_dict()}")
        for side in ("dev", "test"):
            print(f"\n{column} = {side}\n{payer_code_table(df, side, column).to_string()}")
