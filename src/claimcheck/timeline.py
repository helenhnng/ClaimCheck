"""Running state built from earlier claims, in submission order.

Three rules depend on what was submitted before a claim:

- **Duplicate (D05):** the same payer, patient, service and date of service was
  already submitted, whatever happened to that earlier claim.
- **Authorization balance (D02):** units authorized minus the units of earlier
  *paid* claims on that authorization.
- **Daily maximum (D06):** units of earlier *paid* claims for that patient and
  date of service (payers with a daily limit only).

Claims are walked by ``submitted_date``, then ``claim_id`` (the tie-break for
claims submitted on the same day is an assumption; the data has no time of day).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TimelineState:
    duplicate_key: list[str]
    seen: dict[tuple, str] = field(default_factory=dict)            # key -> first claim_id
    auth_used: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_paid: dict[tuple, int] = field(default_factory=lambda: defaultdict(int))

    def _dup_key(self, claim: dict) -> tuple:
        return tuple(claim[name] for name in self.duplicate_key)

    @staticmethod
    def _day_key(claim: dict) -> tuple:
        return (claim["payer_id"], claim["patient_id"], claim["date_of_service"])

    # --- read the state before a claim -------------------------------------
    def earlier_claim_with_same_key(self, claim: dict) -> str | None:
        return self.seen.get(self._dup_key(claim))

    def auth_remaining(self, auth: dict | None) -> int | None:
        if auth is None:
            return None
        return auth["units_authorized"] - self.auth_used[auth["auth_id"]]

    def daily_paid_units(self, claim: dict) -> int:
        return self.daily_paid[self._day_key(claim)]

    # --- update the state after a claim ------------------------------------
    def record(self, claim: dict, paid: bool) -> None:
        """Register a submitted claim. Only a paid claim uses up units."""
        self.seen.setdefault(self._dup_key(claim), claim["claim_id"])
        if paid:
            if claim["auth_id"] is not None:
                self.auth_used[claim["auth_id"]] += claim["units"]
            self.daily_paid[self._day_key(claim)] += claim["units"]
