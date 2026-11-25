"""Predict paid/denied, the denial code, the rule broken and the fix.

    python -m claimcheck.predict

Writes ``outputs/predictions.csv`` (``claim_id,status,denial_code``) and
``outputs/predictions_detailed.csv`` for the claims in ``claims_to_check.csv``.
Decisions come from rules only. D99 is never predicted: it cannot be.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from claimcheck import paths, review
from claimcheck.config import default_config, precedence_for
from claimcheck.data import DataError, clean_claims, load_auths, load_claims, load_evv, read_raw_csv
from claimcheck.evv import NO_EVV, EvvDay, build_evv_index
from claimcheck.rules import ALLOWED_CLAIM_FIELDS, ClaimContext, evaluate_rules, pick_hit
from claimcheck.timeline import TimelineState

PREDICTION_COLUMNS = ["claim_id", "status", "denial_code"]
DETAIL_COLUMNS = PREDICTION_COLUMNS + [
    "payer_id", "all_hits", "rule_id", "message", "citation", "fix",
    "confidence", "needs_review", "review_reason", "action",
    "auth_remaining_before", "daily_paid_before", "dup_of_claim_id",
]


@dataclass
class Lookups:
    """Read-only reference data, indexed once."""
    evv: dict[tuple, EvvDay]
    auth_by_id: dict[str, dict]
    auths_by_key: dict[tuple, list[dict]]   # (payer, patient, service) -> authorizations


def build_lookups(evv: pd.DataFrame, auths: pd.DataFrame, cfg: dict) -> Lookups:
    auth_rows = auths.to_dict("records")
    by_key: dict[tuple, list[dict]] = {}
    for auth in auth_rows:
        by_key.setdefault((auth["payer_id"], auth["patient_id"], auth["service_code"]), []).append(auth)
    return Lookups(
        evv=build_evv_index(evv, cfg["global"]),
        auth_by_id={a["auth_id"]: a for a in auth_rows},
        auths_by_key=by_key,
    )


def claim_records(claims: pd.DataFrame) -> list[dict]:
    """Claims as dicts holding only the fields a rule may read.

    Outcome columns (``status``, ``denial_code``) and ``remark`` never reach a rule.
    """
    columns = [c for c in claims.columns if c in ALLOWED_CLAIM_FIELDS]
    ordered = claims.sort_values(["submitted_date", "claim_id"])
    return ordered[columns].to_dict("records")


def context_for(claim: dict, lookups: Lookups, state: TimelineState | None = None) -> ClaimContext:
    dos = claim["date_of_service"]
    candidates = [
        a for a in lookups.auths_by_key.get((claim["payer_id"], claim["patient_id"], claim["service_code"]), [])
        if a["start_date"] <= dos <= a["end_date"]
    ]
    ctx = ClaimContext(
        evv=lookups.evv.get((claim["patient_id"], claim["service_code"], dos), NO_EVV),
        auth=lookups.auth_by_id.get(claim["auth_id"]) if claim["auth_id"] else None,
        candidate_auths=candidates,
    )
    if state is not None:
        ctx.dup_of_claim_id = state.earlier_claim_with_same_key(claim)
        ctx.auth_remaining_before = state.auth_remaining(ctx.auth)
        ctx.daily_paid_before = state.daily_paid_units(claim)
    return ctx


def decide(claim: dict, ctx: ClaimContext, cfg: dict) -> dict:
    """One detailed prediction row for one claim."""
    hits = evaluate_rules(claim, ctx, cfg)
    chosen = pick_hit(hits, precedence_for(cfg, claim["payer_id"]))
    reasons = review.review_reasons(claim, ctx, chosen, cfg)
    return {
        "claim_id": claim["claim_id"],
        "status": "paid" if chosen is None else "denied",
        "denial_code": "" if chosen is None else chosen.denial_code,
        "payer_id": claim["payer_id"],
        "all_hits": "|".join(h.denial_code for h in hits),
        "rule_id": "" if chosen is None else chosen.rule_id,
        "message": "No rule broken." if chosen is None else chosen.message,
        "citation": "" if chosen is None else chosen.citation,
        "fix": "" if chosen is None else chosen.fix,
        "confidence": review.confidence(hits, reasons),
        "needs_review": bool(reasons),
        "review_reason": "; ".join(reasons),
        "action": review.action(chosen, reasons),
        "auth_remaining_before": ctx.auth_remaining_before,
        "daily_paid_before": ctx.daily_paid_before,
        "dup_of_claim_id": ctx.dup_of_claim_id or "",
    }


def predict_claims(claims: pd.DataFrame, evv: pd.DataFrame, auths: pd.DataFrame,
                   cfg: dict | None = None, known_status: dict[str, str] | None = None) -> pd.DataFrame:
    """Detailed predictions for every claim, walking them in submission order.

    ``claims`` should be the whole timeline (history and claims to check
    together), because duplicates, authorization balances and daily totals
    depend on earlier claims. After each claim the running state is updated:
    with the payer's real decision where one is known (``known_status``, i.e.
    history claims), otherwise with our own prediction.
    """
    cfg = cfg or default_config()
    known_status = known_status or {}
    lookups = build_lookups(evv, auths, cfg)
    state = TimelineState(duplicate_key=cfg["global"]["duplicate_key"])
    rows = []
    for claim in claim_records(claims):
        row = decide(claim, context_for(claim, lookups, state), cfg)
        rows.append(row)
        state.record(claim, paid=known_status.get(claim["claim_id"], row["status"]) == "paid")
    return pd.DataFrame(rows, columns=DETAIL_COLUMNS)


def load_timeline() -> tuple[pd.DataFrame, dict[str, str]]:
    """All claims (history + to check) and the known outcome of the history claims."""
    history, to_check = load_claims("history"), load_claims("to_check")
    known = dict(zip(history["claim_id"], history["status"]))
    shared = [c for c in to_check.columns if c in history.columns]
    return pd.concat([history[shared], to_check[shared]], ignore_index=True), known


def validate_predictions(pred: pd.DataFrame, expected_ids: set[str]) -> None:
    """Raise if the submission file would be malformed."""
    if list(pred.columns) != PREDICTION_COLUMNS:
        raise ValueError(f"predictions must have columns {PREDICTION_COLUMNS}")
    if pred["claim_id"].duplicated().any() or set(pred["claim_id"]) != expected_ids:
        raise ValueError("predictions must hold each claim to check exactly once")
    if not set(pred["status"]) <= {"paid", "denied"}:
        raise ValueError("status must be paid or denied")
    if ((pred["status"] == "paid") != (pred["denial_code"] == "")).any():
        raise ValueError("denial_code must be blank if and only if status is paid")


def check_claims(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Check a raw file of unsubmitted claims. Returns ``(claims, detailed, report)``.

    ``raw`` holds text cells in the layout of ``claims_to_check.csv`` (see
    ``data.read_raw_csv``). The claims are cleaned, placed on the timeline after
    the adjudicated history, and run through the rules. ``claims`` is the
    cleaned input, ``detailed`` one prediction row per claim (sorted by
    ``claim_id``), ``report`` the cleaning summary.
    """
    claims, report = clean_claims(raw, "to_check")
    if claims.empty:
        raise DataError("The file has no claims.")
    history = load_claims("history")
    already = sorted(set(claims["claim_id"]) & set(history["claim_id"]))
    if already:
        raise DataError(
            f"{len(already)} claim(s) are already in the adjudicated history, e.g. {already[:5]}. "
            "Upload only claims that have not been submitted."
        )
    known = dict(zip(history["claim_id"], history["status"]))
    timeline = pd.concat([history[list(claims.columns)], claims], ignore_index=True)
    everything = predict_claims(timeline, load_evv(), load_auths(), known_status=known)
    detailed = everything[everything["claim_id"].isin(set(claims["claim_id"]))]
    detailed = detailed.sort_values("claim_id").reset_index(drop=True)
    validate_predictions(detailed[PREDICTION_COLUMNS], set(claims["claim_id"]))
    return claims, detailed, report


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    _, detailed, _ = check_claims(read_raw_csv(paths.CLAIMS_TO_CHECK_CSV))
    predictions = detailed[PREDICTION_COLUMNS]
    predictions.to_csv(paths.output_path("predictions.csv"), index=False)
    detailed.to_csv(paths.output_path("predictions_detailed.csv"), index=False)
    print(f"Wrote {len(predictions)} predictions to outputs/predictions.csv")
    print("By status:", detailed["status"].value_counts().to_dict())
    print("By code:  ", detailed.loc[detailed["denial_code"] != "", "denial_code"].value_counts().to_dict())
    print("By action:", detailed["action"].value_counts().to_dict())


if __name__ == "__main__":
    main()
