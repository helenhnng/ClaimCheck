"""Score predictions against the history outcomes.

    python -m claimcheck.evaluate [--split dev|test]

Writes ``outputs/metrics_<split>.md``. Use ``dev`` while building. ``test`` is
scored once, at the end, and never tuned against.
"""
from __future__ import annotations

import argparse

import pandas as pd

from claimcheck import paths
from claimcheck.data import load_auths, load_claims, load_evv
from claimcheck.predict import predict_claims
from claimcheck.split import attach_split

UNPREDICTABLE = "D99"


def scored_frame(split: str, cfg: dict | None = None) -> pd.DataFrame:
    """True and predicted outcome for each history claim on one side of the split."""
    history = attach_split(load_claims("history"))
    predicted = predict_claims(history, load_evv(), load_auths(), cfg)
    df = history[["claim_id", "payer_id", "status", "denial_code", "split"]].merge(
        predicted[["claim_id", "status", "denial_code", "all_hits", "needs_review", "action"]],
        on="claim_id", suffixes=("_true", "_pred"), validate="one_to_one",
    )
    df["code_true"] = df["denial_code_true"].fillna("PAID")
    df["code_pred"] = df["denial_code_pred"].replace("", "PAID")
    return df[df["split"] == split].reset_index(drop=True)


def metrics(df: pd.DataFrame) -> dict:
    true_denied = df["status_true"] == "denied"
    pred_denied = df["status_pred"] == "denied"
    tp = int((true_denied & pred_denied).sum())
    per_code = []
    for code in sorted(set(df["code_true"]) | set(df["code_pred"])):
        support = int((df["code_true"] == code).sum())
        predicted = int((df["code_pred"] == code).sum())
        correct = int(((df["code_true"] == code) & (df["code_pred"] == code)).sum())
        per_code.append({
            "code": code, "support": support, "predicted": predicted, "correct": correct,
            "precision": correct / predicted if predicted else None,
            "recall": correct / support if support else None,
        })
    errors = (
        df[df["code_true"] != df["code_pred"]]
        .groupby(["code_true", "code_pred"]).size().sort_values(ascending=False)
        .rename("claims").reset_index()
    )
    return {
        "claims": len(df),
        "status_accuracy": float((df["status_true"] == df["status_pred"]).mean()),
        "denied_precision": tp / int(pred_denied.sum()) if pred_denied.any() else None,
        "denied_recall": tp / int(true_denied.sum()) if true_denied.any() else None,
        "missed_denials": int((true_denied & ~pred_denied).sum()),
        "false_alarms": int((~true_denied & pred_denied).sum()),
        "exact_code_accuracy": float((df["code_true"] == df["code_pred"]).mean()),
        "d99_claims": int((df["code_true"] == UNPREDICTABLE).sum()),
        "review_rate": float(df["needs_review"].mean()),
        "per_code": per_code,
        "errors": errors,
        "confusion": pd.crosstab(df["code_true"], df["code_pred"]),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def to_markdown(m: dict, split: str) -> str:
    ceiling = 1 - m["d99_claims"] / m["claims"]
    lines = [
        f"# ClaimCheck metrics: {split} split",
        "",
        f"- Claims: {m['claims']}",
        f"- Paid/denied accuracy: {_pct(m['status_accuracy'])}",
        f"- Denied precision: {_pct(m['denied_precision'])} | recall: {_pct(m['denied_recall'])}",
        f"- Missed denials (predicted paid, was denied): {m['missed_denials']}",
        f"- False alarms (predicted denied, was paid): {m['false_alarms']}",
        f"- Exact-code accuracy (paid counts as a code): {_pct(m['exact_code_accuracy'])}",
        f"- Ceiling: {m['d99_claims']} claims are D99 (unpredictable), so exact-code accuracy cannot exceed {_pct(ceiling)}",
        f"- Routed to human review: {_pct(m['review_rate'])}",
        "",
        "## Per code",
        "| Code | Actual | Predicted | Correct | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['code']} | {r['support']} | {r['predicted']} | {r['correct']} | {_pct(r['precision'])} | {_pct(r['recall'])} |"
        for r in m["per_code"]
    ]
    lines += ["", "## Largest error groups", "| Actual | Predicted | Claims |", "|---|---|---|"]
    lines += [f"| {r.code_true} | {r.code_pred} | {r.claims} |" for r in m["errors"].head(12).itertuples()]
    lines += ["", "## Confusion matrix (rows actual, columns predicted)", "", "```",
              m["confusion"].to_string(), "```", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()
    df = scored_frame(args.split)
    report = to_markdown(metrics(df), args.split)
    paths.output_path(f"metrics_{args.split}.md").write_text(report, encoding="utf-8")
    if args.split == "dev":
        wrong = df[df["code_true"] != df["code_pred"]]
        wrong.to_csv(paths.output_path("mistakes_dev.csv"), index=False)
    print(report)


if __name__ == "__main__":
    main()
