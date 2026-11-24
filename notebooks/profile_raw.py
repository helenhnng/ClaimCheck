"""One-off profile of the raw CSVs (M1). Read-only: prints per-column quirks.

Run: .venv/bin/python notebooks/profile_raw.py
"""
import pandas as pd

from claimcheck import paths as p


def shape_of(series: pd.Series) -> pd.Series:
    return series.str.replace(r"[A-Za-z]", "a", regex=True).str.replace(r"\d", "9", regex=True)


def profile(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    print(f"\n##### {path.name} {df.shape} exact dup rows: {df.duplicated().sum()}", flush=True)
    for col in df.columns:
        s = df[col]
        info = (
            f"  {col}: nunique={s.nunique()} blank={(s.str.strip() == '').sum()} "
            f"whitespace={(s != s.str.strip()).sum()}"
        )
        if s.nunique() <= 25:
            info += f" values={s.value_counts().to_dict()!r}"
        else:
            info += f" shapes={shape_of(s).value_counts().head(8).to_dict()!r}"
        print(info, flush=True)
    return df


if __name__ == "__main__":
    h = profile(p.CLAIMS_HISTORY_CSV)
    t = profile(p.CLAIMS_TO_CHECK_CSV)
    a = profile(p.AUTHORIZATIONS_CSV)
    e = profile(p.EVV_VISITS_CSV)
    print("\nhistory claim_id dups:", h.claim_id.duplicated().sum(),
          "after dropping exact dup rows:", h.drop_duplicates().claim_id.duplicated().sum())
    print("to_check claim_id dups:", t.claim_id.duplicated().sum(),
          "ids in both files:", len(set(h.claim_id) & set(t.claim_id)))
    print("auth_id dups:", a.auth_id.duplicated().sum())
    print("visit_id dups:", e.visit_id.duplicated().sum())
