# ClaimCheck: claim approval/denial predictor (Exchange4Health take-home)

## What it does
Predicts, for each claim in `claims_to_check.csv`, whether the payer will pay or deny it and which denial code will be reported. Writes `predictions.csv` (`claim_id,status,denial_code`).

## How to run
```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -e .
export ANTHROPIC_API_KEY=...   # only if the LLM layer is used; never commit it
python -m claimcheck.predict   # TODO: entry point
pytest
```
Raw data is read from `1. RAW DATA/` and is never modified.

## Assumptions
_To be filled in as the build progresses._

## Tools used
Claude Code (Sonnet 5.5 / Opus 5.5). _Add anything else._

## Layout
- `PLANNING.md`: roadmap and checklist
- `docs/design.md`: system design and diagram
- `src/claimcheck/`: code
- `tests/`: unit tests and backtests
- `outputs/`: generated files (`predictions.csv`, metrics)
