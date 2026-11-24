"""Load and validate ``rules_config.yaml`` and answer date-dependent lookups."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from claimcheck import paths

ROUNDING_METHODS = {"floor", "eight_minute_rule"}
AGGREGATIONS = {"sum_then_round", "round_then_sum"}
FILING_BOUNDARIES = {"gt", "ge"}
DAY_TYPES = {"all", "weekday", "weekend"}
KNOWN_CODES = {f"D{n:02d}" for n in range(1, 11)}


class ConfigError(ValueError):
    """The rules config is missing something or holds an unknown value."""


def validate(cfg: dict) -> dict:
    for key in ("global", "payers"):
        if key not in cfg:
            raise ConfigError(f"rules config: missing section '{key}'")
    g = cfg["global"]
    if g["evv_aggregation"] not in AGGREGATIONS:
        raise ConfigError(f"evv_aggregation must be one of {sorted(AGGREGATIONS)}")
    if g["filing_boundary"] not in FILING_BOUNDARIES:
        raise ConfigError(f"filing_boundary must be one of {sorted(FILING_BOUNDARIES)}")
    unknown = set(g["precedence"]) - KNOWN_CODES
    if unknown or len(set(g["precedence"])) != len(g["precedence"]):
        raise ConfigError(f"precedence has unknown or repeated codes: {sorted(unknown)}")
    for payer_id, payer in cfg["payers"].items():
        if payer["rounding"] not in ROUNDING_METHODS:
            raise ConfigError(f"{payer_id}: rounding must be one of {sorted(ROUNDING_METHODS)}")
        for rule in payer.get("modifier_rules") or []:
            if rule["days"] not in DAY_TYPES:
                raise ConfigError(f"{payer_id}: modifier rule days must be one of {sorted(DAY_TYPES)}")
        for key in ("evv", "units", "auth", "duplicate"):
            if key not in payer.get("citations", {}):
                raise ConfigError(f"{payer_id}: missing citation '{key}'")
    return cfg


def load_config(path: Path | None = None) -> dict:
    """Read and validate the rules config. Returns a fresh dict each call."""
    with open(path or paths.RULES_CONFIG_YAML, encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh))


@lru_cache(maxsize=1)
def default_config() -> dict:
    """The packaged config, loaded once. Treat as read-only."""
    return load_config()


def payer_config(cfg: dict, payer_id: str) -> dict:
    try:
        return cfg["payers"][payer_id]
    except KeyError:
        raise ConfigError(f"No rules configured for payer {payer_id!r}") from None


def _in_window(entry: dict, dos: date) -> bool:
    start, end = entry.get("dos_from"), entry.get("dos_to")
    return (start is None or dos >= start) and (end is None or dos <= end)


def filing_rule(cfg: dict, payer_id: str, dos: date) -> dict | None:
    """The timely-filing entry in force for this date of service, or ``None``."""
    matches = [e for e in payer_config(cfg, payer_id).get("timely_filing") or [] if _in_window(e, dos)]
    if len(matches) > 1:
        raise ConfigError(f"{payer_id}: overlapping timely_filing entries for {dos}")
    return matches[0] if matches else None


def modifier_rule(cfg: dict, payer_id: str, service_code: str, dos: date) -> dict | None:
    """The modifier requirement for this payer, service and date, or ``None``."""
    day_type = "weekend" if dos.weekday() >= 5 else "weekday"
    matches = [
        r for r in payer_config(cfg, payer_id).get("modifier_rules") or []
        if r["service"] == service_code and _in_window(r, dos) and r["days"] in ("all", day_type)
    ]
    if len(matches) > 1:
        raise ConfigError(f"{payer_id}: overlapping modifier rules for {service_code} on {dos}")
    return matches[0] if matches else None
