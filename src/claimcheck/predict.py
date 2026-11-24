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
from claimcheck.config import default_config
from claimcheck.data import load_auths, load_claims, load_evv
from claimcheck.evv import NO_EVV, EvvDay, build_evv_index
from claimcheck.rules import ALLOWED_CLAIM_FIELDS, ClaimContext, evaluate_rules, pick_hit

PREDICTION_COLUMNS = ["claim_id", "status", "denial_code"]
DETAIL_COLUMNS = PREDICTION_COLUMNS + [
    "payer_id", "all_hits", "rule_id", "message", "citation", "fix",
    "confidence", "needs_review", "review_reason", "action",
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


def context_for(claim: dict, lookups: Lookups) -> ClaimContext:
    dos = claim["date_of_service"]
    candidates = [
        a for a in lookups.auths_by_key.get((claim["payer_id"], claim["patient_id"], claim["service_code"]), [])
        if a["start_date"] <= dos <= a["end_date"]
    ]
    return ClaimContext(
        evv=lookups.evv.get((claim["patient_id"], claim["service_code"], dos), NO_EVV),
        auth=lookups.auth_by_id.get(claim["auth_id"]) if claim["auth_id"] else None,
        candidate_auths=candidates,
    )


def decide(claim: dict, ctx: ClaimContext, cfg: dict) -> dict:
    """One detailed prediction row for one claim."""
    hits = evaluate_rules(claim, ctx, cfg)
    chosen = pick_hit(hits, cfg["global"]["precedence"])
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
    }


def predict_claims(claims: pd.DataFrame, evv: pd.DataFrame, auths: pd.DataFrame,
                   cfg: dict | None = None) -> pd.DataFrame:
    """Detailed predictions for every claim, in submission order."""
    cfg = cfg or default_config()
    lookups = build_lookups(evv, auths, cfg)
    rows = [decide(claim, context_for(claim, lookups), cfg) for claim in claim_records(claims)]
    return pd.DataFrame(rows, columns=DETAIL_COLUMNS)


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


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    to_check = load_claims("to_check")
    detailed = predict_claims(to_check, load_evv(), load_auths())
    detailed = detailed.sort_values("claim_id").reset_index(drop=True)
    predictions = detailed[PREDICTION_COLUMNS]
    validate_predictions(predictions, set(to_check["claim_id"]))
    predictions.to_csv(paths.output_path("predictions.csv"), index=False)
    detailed.to_csv(paths.output_path("predictions_detailed.csv"), index=False)
    print(f"Wrote {len(predictions)} predictions to outputs/predictions.csv")
    print("By status:", detailed["status"].value_counts().to_dict())
    print("By code:  ", detailed.loc[detailed["denial_code"] != "", "denial_code"].value_counts().to_dict())
    print("By action:", detailed["action"].value_counts().to_dict())


if __name__ == "__main__":
    main()
