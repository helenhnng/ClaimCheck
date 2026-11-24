"""EVV evidence per (patient, service, date) and minutes-to-units rounding.

- A visit belongs to its **clock-in date**, even when it runs past midnight.
- Only verified visits count as evidence.
- Same-day visits are summed before rounding (default); the alternative
  (round each visit, then sum) is a config switch so it can be compared on dev.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

EvvKey = tuple[str, str, date]  # (patient_id, service_code, visit date)


@dataclass
class EvvDay:
    """What EVV shows for one patient, service and date."""
    verified_minutes: list[int] = field(default_factory=list)  # one entry per verified visit
    verified_visit_ids: list[str] = field(default_factory=list)
    pending_visit_ids: list[str] = field(default_factory=list)
    rejected_visit_ids: list[str] = field(default_factory=list)

    @property
    def total_verified_minutes(self) -> int:
        return sum(self.verified_minutes)

    @property
    def has_verified(self) -> bool:
        return bool(self.verified_minutes)


NO_EVV = EvvDay()


def round_units(minutes: int, method: str, unit_minutes: int = 15, threshold: int = 8) -> int:
    """Billable units for a number of verified minutes."""
    if minutes < 0:
        raise ValueError(f"Negative minutes: {minutes}")
    whole, remainder = divmod(int(minutes), unit_minutes)
    if method == "floor":
        return whole
    if method == "eight_minute_rule":
        return whole + (1 if remainder >= threshold else 0)
    raise ValueError(f"Unknown rounding method {method!r}")


def supported_units(day: EvvDay, payer_cfg: dict, global_cfg: dict) -> int:
    """Units the verified EVV time supports under this payer's rounding."""
    kwargs = dict(
        method=payer_cfg["rounding"],
        unit_minutes=global_cfg["unit_minutes"],
        threshold=payer_cfg.get("eight_minute_threshold", 8),
    )
    if global_cfg["evv_aggregation"] == "round_then_sum":
        return sum(round_units(m, **kwargs) for m in day.verified_minutes)
    return round_units(day.total_verified_minutes, **kwargs)


def build_evv_index(evv: pd.DataFrame, global_cfg: dict) -> dict[EvvKey, EvvDay]:
    """Index cleaned EVV visits by (patient, service, clock-in date)."""
    valid = set(global_cfg["evv_valid_statuses"])
    pending = set(global_cfg["evv_pending_statuses"])
    index: dict[EvvKey, EvvDay] = {}
    for visit in evv.itertuples(index=False):
        key = (visit.patient_id, visit.service_code, visit.clock_in.date())
        day = index.setdefault(key, EvvDay())
        if visit.verification_status in valid:
            minutes = int((visit.clock_out - visit.clock_in).total_seconds() // 60)
            day.verified_minutes.append(minutes)
            day.verified_visit_ids.append(visit.visit_id)
        elif visit.verification_status in pending:
            day.pending_visit_ids.append(visit.visit_id)
        else:
            day.rejected_visit_ids.append(visit.visit_id)
    return index
