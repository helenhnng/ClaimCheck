"""Project-root-relative paths.

Folder names contain spaces ("1. RAW DATA"), so always use these Path objects
(and quote them if they are ever passed to a shell) instead of building strings.
"""
from __future__ import annotations

import os
from pathlib import Path

RAW_DIR_NAME = "1. RAW DATA"
INSTRUCTIONS_DIR_NAME = "2. INSTRUCTIONS"
WORKING_DIR_NAME = "3. WORKING FOLDER"

ROOT_ENV_VAR = "CLAIMCHECK_ROOT"


def find_project_root(start: Path | None = None) -> Path:
    """Return the project root: the nearest ancestor holding ``1. RAW DATA``.

    ``CLAIMCHECK_ROOT`` overrides the search. Raises if no root is found, so a
    wrong working directory never turns into silently empty data.
    """
    override = os.environ.get(ROOT_ENV_VAR)
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / RAW_DIR_NAME).is_dir():
            raise FileNotFoundError(
                f"{ROOT_ENV_VAR}={override!r} does not contain a '{RAW_DIR_NAME}' folder"
            )
        return root

    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / RAW_DIR_NAME).is_dir():
            return candidate
    raise FileNotFoundError(
        f"Could not find the project root (a folder containing '{RAW_DIR_NAME}') "
        f"above {here}. Set {ROOT_ENV_VAR} to the project folder."
    )


PROJECT_ROOT = find_project_root()

# Read-only inputs. Never write to these.
RAW_DIR = PROJECT_ROOT / RAW_DIR_NAME
INSTRUCTIONS_DIR = PROJECT_ROOT / INSTRUCTIONS_DIR_NAME
WORKING_DIR = PROJECT_ROOT / WORKING_DIR_NAME
PAYER_DOCS_DIR = RAW_DIR / "payers"

CLAIMS_HISTORY_CSV = RAW_DIR / "claims_history.csv"
CLAIMS_TO_CHECK_CSV = RAW_DIR / "claims_to_check.csv"
AUTHORIZATIONS_CSV = RAW_DIR / "authorizations.csv"
EVV_VISITS_CSV = RAW_DIR / "evv_visits.csv"

# Project files.
DOCS_DIR = PROJECT_ROOT / "docs"
PACKAGE_DIR = Path(__file__).resolve().parent
RULES_CONFIG_YAML = PACKAGE_DIR / "rules_config.yaml"

# The only place generated files may go.
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def output_path(name: str) -> Path:
    """Path of a generated file inside ``outputs/`` (created if missing)."""
    OUTPUTS_DIR.mkdir(exist_ok=True)
    return OUTPUTS_DIR / name
