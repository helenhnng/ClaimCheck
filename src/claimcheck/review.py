"""Tier 4: what a person must look at, and the recommended action.

The biller always decides. This only sorts claims into ``submit``,
``fix_then_submit``, ``hold`` and ``review``.
"""
from __future__ import annotations

from claimcheck.rules import ClaimContext, RuleHit


def confidence(hits: list[RuleHit], review_reasons: list[str]) -> str:
    """``high``: one hit or none. ``medium``: several hits, or a review reason."""
    if len(hits) > 1 or review_reasons:
        return "medium"
    return "high"


def review_reasons(claim: dict, ctx: ClaimContext, chosen: RuleHit | None, cfg: dict) -> list[str]:
    reasons = []
    if claim["frequency_code"] == 7:
        reasons.append("Corrected claim (frequency 7): no history examples to check the prediction against")
    if chosen is not None and chosen.denial_code == "D10":
        reasons.append("Contract-specific rule inferred from history, not from the payer handbook")
    margin = cfg["global"]["near_limit_units"]
    if ctx.auth_remaining_before is not None and chosen is None:
        left = ctx.auth_remaining_before - claim["units"]
        if 0 <= left <= margin:
            reasons.append(f"Only {left} unit(s) would remain on the authorization; depends on earlier claims being paid")
    # Only when earlier paid claims exist for the day: a single claim near the limit
    # depends on nothing we predicted.
    if ctx.daily_paid_before and chosen is None:
        limit = (cfg["payers"][claim["payer_id"]].get("daily_max_units") or {}).get("limit")
        if limit is not None and 0 <= limit - ctx.daily_paid_before - claim["units"] <= margin:
            reasons.append("Close to the daily unit maximum; depends on earlier claims being paid")
    return reasons


def is_hold(chosen: RuleHit | None) -> bool:
    """Pending EVV: the advice is to wait, not to write the claim off."""
    return (
        chosen is not None
        and chosen.rule_id == "evv_missing"
        and bool(chosen.details.get("pending_visits"))
    )


def action(chosen: RuleHit | None, reasons: list[str]) -> str:
    if is_hold(chosen):
        return "hold"
    if reasons:
        return "review"
    return "submit" if chosen is None else "fix_then_submit"
