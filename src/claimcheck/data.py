"""Tier 0: load and clean the raw CSVs.

These loaders are the integration seam: the only code that knows the data comes
from CSV files. In production they would read the platform database.

Cleaning never guesses. A payer name, date or number that cannot be mapped or
parsed raises ``DataError`` naming the column and the offending values. The only
rows ever dropped are exact duplicate rows, and the count is reported.

``remark`` is written by the payer *after* the decision, so ``load_claims``
never returns it. ``load_remarks`` exists for rule discovery on the dev split
only; it must never feed a rule or a model.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from claimcheck import paths

log = logging.getLogger(__name__)

ClaimKind = Literal["history", "to_check"]


class DataError(ValueError):
    """Raw data that cannot be cleaned without guessing."""


# --- reference values -------------------------------------------------------

PAYER_ALIASES: dict[str, str] = {
    "PY01": "PY01",
    "NORTHWIND HP": "PY01",
    "Northwind Health Plan": "PY01",
    "PY02": "PY02",
    "Harbor Medicaid Plan": "PY02",
    "Harbor Medicaid": "PY02",
    "PY03": "PY03",
    "SUMMIT CARE": "PY03",
    "Summit Care Partners": "PY03",
}

# ISO first; the US format is month/day/year (docs/findings.md records the check).
DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%m/%d/%Y")
DATETIME_FORMAT = "%Y-%m-%d %H:%M"

FREQUENCY_CODES = {1, 7}
CLAIM_STATUSES = {"paid", "denied"}
EVV_STATUSES = {"verified", "rejected", "manual_edit_pending"}

CLAIM_COLUMNS = [
    "claim_id", "agency_id", "payer", "patient_id", "service_code",
    "date_of_service", "submitted_date", "units", "auth_id", "modifier",
    "frequency_code", "original_claim_id", "billed_amount",
]
OUTCOME_COLUMNS = ["status", "paid_amount", "denial_code", "remark"]
AUTH_COLUMNS = [
    "auth_id", "patient_id", "payer_id", "service_code",
    "start_date", "end_date", "units_authorized",
]
EVV_COLUMNS = [
    "visit_id", "caregiver_id", "patient_id", "service_code",
    "clock_in", "clock_out", "verification_status",
]


# --- value-level cleaners (pure) --------------------------------------------

def normalise_payer(value: str) -> str:
    """Map a payer name or id to ``PY01``/``PY02``/``PY03``. Raises on unknown."""
    key = value.strip() if isinstance(value, str) else value
    try:
        return PAYER_ALIASES[key]
    except (KeyError, TypeError):
        raise DataError(f"Unknown payer {value!r}; add it to PAYER_ALIASES") from None


def normalise_code(value: Any) -> str | None:
    """Strip and upper-case a service code or modifier. Empty becomes ``None``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    return text or None


def blank_to_none(value: Any) -> str | None:
    """Strip an identifier, keeping its case. Empty becomes ``None``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: str) -> date:
    """Parse ``2026-06-09`` or ``09/13/2026`` (month/day/year). Raises otherwise."""
    text = value.strip() if isinstance(value, str) else ""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise DataError(f"Unparseable date {value!r}; expected YYYY-MM-DD or MM/DD/YYYY")


def parse_datetime(value: str) -> datetime:
    """Parse an EVV timestamp ``2026-06-09 08:10``. Raises otherwise."""
    try:
        return datetime.strptime(value.strip(), DATETIME_FORMAT)
    except (ValueError, AttributeError):
        raise DataError(f"Unparseable timestamp {value!r}; expected YYYY-MM-DD HH:MM") from None


def parse_int(value: str) -> int:
    """Parse a whole number (``'18'`` or ``'18.0'``). Raises otherwise."""
    try:
        number = float(str(value).strip())
    except ValueError:
        raise DataError(f"Not a number: {value!r}") from None
    if number != int(number):
        raise DataError(f"Not a whole number: {value!r}")
    return int(number)


# --- column helpers ----------------------------------------------------------

def _apply(df: pd.DataFrame, column: str, func) -> pd.Series:
    """Apply a cleaner to a column; on failure, name the column and bad values."""
    values, bad = [], []
    for raw in df[column]:
        try:
            values.append(func(raw))
        except DataError:
            values.append(None)
            bad.append(raw)
    if bad:
        examples = sorted({repr(b) for b in bad})[:5]
        raise DataError(
            f"Column '{column}': {len(bad)} value(s) could not be cleaned, "
            f"e.g. {', '.join(examples)}"
        )
    # dtype=object keeps None, dates and ints exactly as the cleaner returned them.
    return pd.Series(values, index=df.index, dtype=object)


def _changed(before: pd.Series, after: pd.Series) -> int:
    """How many non-empty raw values were altered by cleaning."""
    return int(((before != after.fillna("").astype(str)) & (before.str.strip() != "")).sum())


def _require_columns(df: pd.DataFrame, expected: list[str], name: str) -> None:
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise DataError(f"{name}: missing column(s) {missing}")


def _require_unique(df: pd.DataFrame, column: str, name: str) -> None:
    dupes = df.loc[df[column].duplicated(), column].tolist()
    if dupes:
        raise DataError(f"{name}: '{column}' is not unique, e.g. {dupes[:5]}")


def _require_in(series: pd.Series, allowed: set, column: str) -> None:
    bad = sorted({v for v in series if v not in allowed}, key=repr)
    if bad:
        raise DataError(f"Column '{column}': unexpected value(s) {bad[:5]}; allowed {sorted(allowed, key=repr)}")


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read a CSV with every cell as text, so nothing is coerced silently."""
    if not path.is_file():
        raise FileNotFoundError(f"Raw data file not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --- claims ------------------------------------------------------------------

def clean_claims(raw: pd.DataFrame, kind: ClaimKind) -> tuple[pd.DataFrame, dict]:
    """Clean a raw claims frame. Returns ``(claims, report)``.

    ``raw`` must hold text cells (see ``read_raw_csv``). ``remark`` is not in the
    result.
    """
    if kind not in ("history", "to_check"):
        raise ValueError(f"kind must be 'history' or 'to_check', got {kind!r}")
    expected = CLAIM_COLUMNS + (OUTCOME_COLUMNS if kind == "history" else [])
    _require_columns(raw, expected, f"claims ({kind})")

    report: dict[str, Any] = {"table": f"claims_{kind}", "rows_in": len(raw)}

    deduped = raw.drop_duplicates(keep="first")
    report["exact_duplicate_rows_dropped"] = len(raw) - len(deduped)
    _require_unique(deduped, "claim_id", f"claims ({kind})")

    df = pd.DataFrame(index=deduped.index)
    df["claim_id"] = _apply(deduped, "claim_id", blank_to_none)
    df["agency_id"] = _apply(deduped, "agency_id", blank_to_none)
    df["payer_id"] = _apply(deduped, "payer", normalise_payer)
    df["patient_id"] = _apply(deduped, "patient_id", blank_to_none)
    df["service_code"] = _apply(deduped, "service_code", normalise_code)
    df["date_of_service"] = _apply(deduped, "date_of_service", parse_date)
    df["submitted_date"] = _apply(deduped, "submitted_date", parse_date)
    df["units"] = _apply(deduped, "units", parse_int).astype(int)
    df["auth_id"] = _apply(deduped, "auth_id", blank_to_none)
    df["modifier"] = _apply(deduped, "modifier", normalise_code)
    df["frequency_code"] = _apply(deduped, "frequency_code", parse_int).astype(int)
    df["original_claim_id"] = _apply(deduped, "original_claim_id", blank_to_none)
    df["billed_amount"] = pd.to_numeric(deduped["billed_amount"], errors="raise").astype(float)
    df["source"] = kind

    for column in ("claim_id", "agency_id", "patient_id", "service_code"):
        if df[column].isna().any():
            raise DataError(f"Column '{column}': {int(df[column].isna().sum())} blank value(s)")
    if (df["units"] <= 0).any():
        raise DataError(f"Column 'units': {int((df['units'] <= 0).sum())} non-positive value(s)")
    _require_in(df["frequency_code"], FREQUENCY_CODES, "frequency_code")

    if kind == "history":
        df["status"] = _apply(deduped, "status", lambda v: str(v).strip().lower())
        _require_in(df["status"], CLAIM_STATUSES, "status")
        df["denial_code"] = _apply(deduped, "denial_code", normalise_code)
        df["paid_amount"] = pd.to_numeric(deduped["paid_amount"], errors="raise").astype(float)
        inconsistent = (df["status"] == "paid") != df["denial_code"].isna()
        if inconsistent.any():
            raise DataError(
                f"{int(inconsistent.sum())} claim(s) where denial_code is not blank-iff-paid, "
                f"e.g. {df.loc[inconsistent, 'claim_id'].head(5).tolist()}"
            )

    report.update(
        rows_out=len(df),
        payer_names_mapped=int((deduped["payer"] != df["payer_id"]).sum()),
        payer_mapping={
            raw_name: PAYER_ALIASES[raw_name.strip()]
            for raw_name in sorted(deduped["payer"].unique())
            if raw_name != PAYER_ALIASES[raw_name.strip()]
        },
        service_codes_normalised=_changed(deduped["service_code"], df["service_code"]),
        modifiers_normalised=_changed(deduped["modifier"], df["modifier"]),
        us_format_dates={
            column: int(deduped[column].str.contains("/").sum())
            for column in ("date_of_service", "submitted_date")
        },
        blank_auth_id=int(df["auth_id"].isna().sum()),
        frequency_7=int((df["frequency_code"] == 7).sum()),
        submitted_before_service=int((df["submitted_date"] < df["date_of_service"]).sum()),
    )
    return df.reset_index(drop=True), report


def load_claims(kind: ClaimKind) -> pd.DataFrame:
    """Cleaned claims. ``kind='history'`` adds ``status``, ``denial_code``, ``paid_amount``.

    Never includes ``remark``. The cleaning summary is logged and kept in
    ``df.attrs['cleaning_report']``.
    """
    path = paths.CLAIMS_HISTORY_CSV if kind == "history" else paths.CLAIMS_TO_CHECK_CSV
    df, report = clean_claims(read_raw_csv(path), kind)
    return _finish(df, report)


def load_remarks() -> pd.DataFrame:
    """``claim_id, remark`` for history claims. NOT A FEATURE.

    For discovering rules on the dev split only. ``claims_to_check.csv`` has no
    remarks, so nothing that predicts may read this.
    """
    raw = read_raw_csv(paths.CLAIMS_HISTORY_CSV).drop_duplicates(keep="first")
    _require_columns(raw, ["claim_id", "remark"], "claims (history)")
    _require_unique(raw, "claim_id", "claims (history)")
    out = pd.DataFrame({
        "claim_id": raw["claim_id"].str.strip(),
        "remark": _apply(raw, "remark", blank_to_none),
    })
    return out.reset_index(drop=True)


# --- authorizations ----------------------------------------------------------

def clean_auths(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    _require_columns(raw, AUTH_COLUMNS, "authorizations")
    report: dict[str, Any] = {"table": "authorizations", "rows_in": len(raw)}
    deduped = raw.drop_duplicates(keep="first")
    report["exact_duplicate_rows_dropped"] = len(raw) - len(deduped)
    _require_unique(deduped, "auth_id", "authorizations")

    df = pd.DataFrame(index=deduped.index)
    df["auth_id"] = _apply(deduped, "auth_id", blank_to_none)
    df["patient_id"] = _apply(deduped, "patient_id", blank_to_none)
    df["payer_id"] = _apply(deduped, "payer_id", normalise_payer)
    df["service_code"] = _apply(deduped, "service_code", normalise_code)
    df["start_date"] = _apply(deduped, "start_date", parse_date)
    df["end_date"] = _apply(deduped, "end_date", parse_date)
    df["units_authorized"] = _apply(deduped, "units_authorized", parse_int).astype(int)

    for column in ("auth_id", "patient_id", "service_code"):
        if df[column].isna().any():
            raise DataError(f"Column '{column}': {int(df[column].isna().sum())} blank value(s)")
    if (df["end_date"] < df["start_date"]).any():
        raise DataError("authorizations: end_date before start_date")
    if (df["units_authorized"] < 0).any():
        raise DataError("authorizations: negative units_authorized")

    report.update(
        rows_out=len(df),
        payer_names_mapped=int((deduped["payer_id"] != df["payer_id"]).sum()),
        service_codes_normalised=_changed(deduped["service_code"], df["service_code"]),
        us_format_dates={
            column: int(deduped[column].str.contains("/").sum())
            for column in ("start_date", "end_date")
        },
    )
    return df.reset_index(drop=True), report


def load_auths() -> pd.DataFrame:
    """Cleaned authorizations, one row per ``auth_id``."""
    df, report = clean_auths(read_raw_csv(paths.AUTHORIZATIONS_CSV))
    return _finish(df, report)


# --- EVV visits --------------------------------------------------------------

def clean_evv(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    _require_columns(raw, EVV_COLUMNS, "evv_visits")
    report: dict[str, Any] = {"table": "evv_visits", "rows_in": len(raw)}
    deduped = raw.drop_duplicates(keep="first")
    report["exact_duplicate_rows_dropped"] = len(raw) - len(deduped)
    _require_unique(deduped, "visit_id", "evv_visits")

    df = pd.DataFrame(index=deduped.index)
    df["visit_id"] = _apply(deduped, "visit_id", blank_to_none)
    df["caregiver_id"] = _apply(deduped, "caregiver_id", blank_to_none)
    df["patient_id"] = _apply(deduped, "patient_id", blank_to_none)
    df["service_code"] = _apply(deduped, "service_code", normalise_code)
    df["clock_in"] = _apply(deduped, "clock_in", parse_datetime)
    df["clock_out"] = _apply(deduped, "clock_out", parse_datetime)
    df["verification_status"] = _apply(
        deduped, "verification_status", lambda v: str(v).strip().lower()
    )
    _require_in(df["verification_status"], EVV_STATUSES, "verification_status")

    for column in ("visit_id", "patient_id", "service_code"):
        if df[column].isna().any():
            raise DataError(f"Column '{column}': {int(df[column].isna().sum())} blank value(s)")
    not_after = [o <= i for i, o in zip(df["clock_in"], df["clock_out"])]
    if any(not_after):
        raise DataError(
            f"evv_visits: {sum(not_after)} visit(s) with clock_out not after clock_in, "
            f"e.g. {df.loc[not_after, 'visit_id'].head(5).tolist()}"
        )

    report.update(
        rows_out=len(df),
        service_codes_normalised=_changed(deduped["service_code"], df["service_code"]),
        status_counts=df["verification_status"].value_counts().to_dict(),
        crosses_midnight=int(sum(i.date() != o.date() for i, o in zip(df["clock_in"], df["clock_out"]))),
    )
    return df.reset_index(drop=True), report


def load_evv() -> pd.DataFrame:
    """Cleaned EVV visits, one row per ``visit_id``, timestamps as ``datetime``."""
    df, report = clean_evv(read_raw_csv(paths.EVV_VISITS_CSV))
    return _finish(df, report)


# --- reporting ---------------------------------------------------------------

def _finish(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    log.info("cleaned %s: %s", report["table"], report)
    df.attrs["cleaning_report"] = report
    return df


def cleaning_summary() -> list[dict]:
    """Run every loader and return the cleaning reports (rows in/out, mappings)."""
    frames = [load_claims("history"), load_claims("to_check"), load_auths(), load_evv()]
    return [frame.attrs["cleaning_report"] for frame in frames]


if __name__ == "__main__":
    import json

    print(json.dumps(cleaning_summary(), indent=2, default=str))
