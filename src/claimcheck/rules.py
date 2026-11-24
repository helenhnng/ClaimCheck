"""Tier 1: the rules engine. One small pure function per rule.

Each ``check_xxx(claim, ctx, cfg)`` returns a ``RuleHit`` or ``None``.
``claim`` is a dict of cleaned claim fields. ``ctx`` is a ``ClaimContext`` with
the EVV evidence, the authorization record and (for stateful rules) the
timeline state *before* this claim. ``cfg`` is the loaded rules config.

No rule reads ``remark``, ``status`` or ``denial_code``: those exist only after
the payer decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from claimcheck.config import filing_rule, modifier_rule, payer_config
from claimcheck.evv import EvvDay, supported_units

# Claim fields a rule may read. A test checks that nothing else is touched.
ALLOWED_CLAIM_FIELDS = frozenset({
    "claim_id", "agency_id", "payer_id", "patient_id", "service_code",
    "date_of_service", "submitted_date", "units", "auth_id", "modifier",
    "frequency_code", "original_claim_id", "billed_amount", "source",
})


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    denial_code: str
    message: str
    citation: str
    fix: str
    details: dict = field(default_factory=dict)


@dataclass
class ClaimContext:
    """Everything a rule needs besides the claim itself."""
    evv: EvvDay = field(default_factory=EvvDay)
    auth: dict | None = None                 # the authorization row for claim.auth_id, if any
    candidate_auths: list[dict] = field(default_factory=list)  # auths that would fit this claim
    # Timeline state before this claim (stateful rules):
    dup_of_claim_id: str | None = None
    auth_remaining_before: int | None = None
    daily_paid_before: int | None = None


def _fmt(d) -> str:
    return f"{d.day} {d:%b %Y}"


def _suggest_auth(ctx: ClaimContext) -> str:
    if ctx.candidate_auths:
        ids = ", ".join(a["auth_id"] for a in ctx.candidate_auths)
        return f" {ids} is on file for this patient, service and date."
    return " No authorization on file covers this patient, service and date; request one from the payer."


def check_auth_missing(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    if claim["auth_id"] is not None:
        return None
    return RuleHit(
        rule_id="auth_missing", denial_code="D07",
        message="The claim has no prior authorization number.",
        citation=payer_config(cfg, claim["payer_id"])["citations"]["auth"],
        fix="Add the authorization number before submitting." + _suggest_auth(ctx),
        details={"candidate_auths": [a["auth_id"] for a in ctx.candidate_auths]},
    )


def check_auth_invalid(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    if claim["auth_id"] is None:
        return None  # that is D07, not D08
    auth, problems = ctx.auth, []
    if auth is None:
        problems.append(f"{claim['auth_id']} is not on file")
    else:
        if auth["payer_id"] != claim["payer_id"]:
            problems.append(f"it is a {auth['payer_id']} authorization, the claim is for {claim['payer_id']}")
        if auth["patient_id"] != claim["patient_id"]:
            problems.append(f"it belongs to patient {auth['patient_id']}")
        if auth["service_code"] != claim["service_code"]:
            problems.append(f"it covers {auth['service_code']}, the claim bills {claim['service_code']}")
        if not (auth["start_date"] <= claim["date_of_service"] <= auth["end_date"]):
            problems.append(
                f"it runs {_fmt(auth['start_date'])} to {_fmt(auth['end_date'])}, "
                f"the date of service is {_fmt(claim['date_of_service'])}"
            )
    if not problems:
        return None
    return RuleHit(
        rule_id="auth_invalid", denial_code="D08",
        message=f"Authorization {claim['auth_id']} is not valid for this claim: " + "; ".join(problems) + ".",
        citation=payer_config(cfg, claim["payer_id"])["citations"]["auth"],
        fix="Replace the authorization number." + _suggest_auth(ctx),
        details={"problems": problems, "candidate_auths": [a["auth_id"] for a in ctx.candidate_auths]},
    )


def check_timely_filing(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    rule = filing_rule(cfg, claim["payer_id"], claim["date_of_service"])
    if rule is None:
        return None
    days = (claim["submitted_date"] - claim["date_of_service"]).days
    limit = rule["days"]
    late = days >= limit if cfg["global"]["filing_boundary"] == "ge" else days > limit
    if not late:
        return None
    return RuleHit(
        rule_id="timely_filing", denial_code="D03",
        message=f"Submitted {days} days after the date of service; the limit is {limit} days.",
        citation=rule["citation"],
        fix=(
            f"Past the {limit}-day filing limit by {days - limit} day(s). Resubmitting will not help; "
            "consider a write-off, or an appeal if there is proof of earlier submission."
        ),
        details={"days": days, "limit": limit},
    )


def check_evv_missing(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    if ctx.evv.has_verified:
        return None
    citation = payer_config(cfg, claim["payer_id"])["citations"]["evv"]
    if ctx.evv.pending_visit_ids:
        visits = ", ".join(ctx.evv.pending_visit_ids)
        message = f"The only EVV visit for this date ({visits}) is awaiting verification after a manual edit."
        fix = f"Hold: do not submit yet. Submit once {visits} is verified."
    elif ctx.evv.rejected_visit_ids:
        visits = ", ".join(ctx.evv.rejected_visit_ids)
        message = f"The EVV visit for this date ({visits}) was rejected."
        fix = f"Correct and re-verify visit {visits}, or do not bill this date."
    else:
        message = "No EVV visit is recorded for this patient, service and date of service."
        fix = "Check the date of service and service code against the visit record; bill only verified visits."
    return RuleHit(
        rule_id="evv_missing", denial_code="D01", message=message, citation=citation, fix=fix,
        details={"pending_visits": list(ctx.evv.pending_visit_ids),
                 "rejected_visits": list(ctx.evv.rejected_visit_ids)},
    )


def check_modifier(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    rule = modifier_rule(cfg, claim["payer_id"], claim["service_code"], claim["date_of_service"])
    if rule is None or claim["modifier"] == rule["required"]:
        return None
    required, dos = rule["required"], claim["date_of_service"]
    found = claim["modifier"] or "no modifier"
    return RuleHit(
        rule_id="modifier", denial_code="D04",
        message=f"{claim['service_code']} on {dos:%A} {_fmt(dos)} needs modifier {required}; the claim has {found}.",
        citation=rule["citation"],
        fix=f"Change the modifier to {required}.",
        details={"required": required, "found": claim["modifier"]},
    )


def check_evv_units(claim: dict, ctx: ClaimContext, cfg: dict) -> RuleHit | None:
    if not ctx.evv.has_verified:
        return None  # that is D01
    payer = payer_config(cfg, claim["payer_id"])
    supported = supported_units(ctx.evv, payer, cfg["global"])
    if claim["units"] <= supported:
        return None
    minutes = ctx.evv.total_verified_minutes
    rounding = "8-minute rule" if payer["rounding"] == "eight_minute_rule" else "complete 15-minute units only"
    return RuleHit(
        rule_id="evv_units", denial_code="D09",
        message=(
            f"Billed {claim['units']} units, but {minutes} verified minutes support only "
            f"{supported} ({rounding})."
        ),
        citation=payer["citations"]["units"],
        fix=f"Reduce the claim to {supported} units, or correct the EVV record if the visit was longer.",
        details={"verified_minutes": minutes, "supported_units": supported},
    )


Rule = Callable[[dict, ClaimContext, dict], "RuleHit | None"]

# Stateless rules: need only the claim, its EVV and its authorization.
STATELESS_RULES: list[Rule] = [
    check_auth_missing, check_auth_invalid, check_timely_filing,
    check_evv_missing, check_modifier, check_evv_units,
]
ALL_RULES: list[Rule] = list(STATELESS_RULES)


def evaluate_rules(claim: dict[str, Any], ctx: ClaimContext, cfg: dict,
                   rules: list[Rule] | None = None) -> list[RuleHit]:
    """Every rule the claim breaks (precedence then picks the one reported)."""
    hits = [rule(claim, ctx, cfg) for rule in (rules or ALL_RULES)]
    return [hit for hit in hits if hit is not None]


def pick_hit(hits: list[RuleHit], precedence: list[str]) -> RuleHit | None:
    """The hit whose code comes first in the precedence order."""
    if not hits:
        return None
    unknown = [h.denial_code for h in hits if h.denial_code not in precedence]
    if unknown:
        raise ValueError(f"Codes missing from the precedence order: {unknown}")
    return min(hits, key=lambda h: precedence.index(h.denial_code))
