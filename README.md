# ClaimCheck: pre-submission claim checker (Exchange4Health take-home)

## What it does
ClaimCheck reads a home-care agency's unsubmitted claims and, for each one, predicts whether the payer will **pay or deny** it and which **denial code** (D01 to D10) it will report. For every predicted denial it gives the **rule broken**, a **citation** to the payer document, a **suggested fix**, and an **action** for the biller: `submit`, `fix_then_submit`, `hold` or `review`.

The biller decides. Nothing is changed or submitted automatically.

Example output for one claim:

> **C019627, PY02, denied D08.** Authorization AUTH13917 is not valid for this claim: it runs 1 Jun 2026 to 31 Aug 2026, the date of service is 30 Sep 2026. *(PY02 Billing Guide, Authorizations)* **Fix:** Replace the authorization number. AUTH13920 is on file for this patient, service and date.

## Results
Scored on past claims whose outcome is known. 70% (dev) was used to build and check the rules; 30% (test) was held back and scored once at the end.

| Measure | Dev (2,681) | Test (1,149) |
|---|---|---|
| Paid/denied accuracy | 98.4% | 98.4% |
| Denied precision | 99.9% | 100.0% |
| Denied recall | 94.4% | 94.5% |
| False alarms (predicted denied, was paid) | 1 | 0 |
| Missed denials (predicted paid, was denied) | 43 | 18 |
| Exact-code accuracy | 98.1% | 98.0% |
| Best possible exact-code accuracy | 98.1% | 98.1% |

- **Every missed denial is a D99** ("Denied - contact payer" / "Under review"). D99 cannot be predicted from the data, so ClaimCheck never predicts it. That caps exact-code accuracy at 98.1%.
- On test, the only other errors are 4 claims the payer coded D99 that we call D10 (the payer's remark names the D10 cause), and 1 claim coded D03 that we call D05.
- Per-code tables: `outputs/metrics_dev.md`, `outputs/metrics_test.md`.

Predictions for the 546 claims to check: 377 paid, 169 denied. Actions: 360 submit, 147 fix then submit, 35 review, 4 hold.

## How to run
Needs Python 3.11 or later.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pytest                                    # 152 tests
python -m claimcheck.predict              # writes outputs/predictions.csv and predictions_detailed.csv
python -m claimcheck.evaluate --split dev # writes outputs/metrics_dev.md
streamlit run app/streamlit_app.py        # demo screen at http://localhost:8501
```

The demo screen shows the totals by action and by denial code, a filterable list of claims, and for any claim the verdict, rule broken, source, suggested fix, and the EVV visits and authorization behind the decision.

Raw data is read from `1. RAW DATA/` and is never modified (a test compares file hashes on every run). No API key is needed: no language model is called at run time.

Note: if the project sits in an iCloud-synced folder (such as Desktop), name the environment `.venv.nosync` so iCloud does not offload its files.

## How it works
1. **Clean** (`data.py`): payer names mapped to PY01/PY02/PY03, codes and modifiers stripped and upper-cased, two date formats parsed, 32 exact duplicate rows dropped. Anything that cannot be parsed raises an error; nothing is guessed.
2. **Timeline** (`timeline.py`): past claims and claims to check are walked together in submission order, keeping running totals: which claims were already billed, units left on each authorization, and paid units per patient per day.
3. **Rules** (`rules.py`, parameters in `rules_config.yaml`): ten checks, one per denial code. Every payer-specific number (filing limits, rounding, modifier dates, the daily maximum) lives in the settings file with its effective dates, so a new payer bulletin is a settings change, not a code change.
4. **Code order**: when a claim breaks several rules the payer reports one code. The order was set from dev claims that break two or more rules.
5. **Review routing** (`review.py`): decides what a person must look at.

| Code | Check |
|---|---|
| D01 | No verified EVV visit for the patient, service and date of service |
| D02 | Units exceed what is left on the authorization after earlier paid claims |
| D03 | Submitted after the payer's filing limit (PY01 30 days, 45 from 1 Aug 2026; PY03 60; PY02 none) |
| D04 | PY02 T1019 without U2 (weekends from 1 Sep 2026: U3) |
| D05 | Same payer, patient, service and date of service as an earlier claim |
| D06 | PY02: would take the patient's paid units for the day above 32 |
| D07 | No authorization number |
| D08 | Authorization is for another patient or service, or does not cover the date |
| D09 | Units exceed verified EVV time (PY01 8-minute rule; PY02 and PY03 complete units only) |
| D10 | PY03, date of service from 1 Jul 2026: units are not a whole number of hours |

## Human in the loop
- `hold` (4 claims): the only EVV visit is awaiting verification. The advice is to wait, not to write the claim off.
- `review` (35 claims): corrected claims (14), predicted D10 (16), and paid claims within 2 units of an authorization or daily limit (5), which depend on earlier predictions being right.
- D99 denials cannot be foreseen; about 2% of claims will be denied for reasons no rule explains.

## Assumptions and known limits
- **Tie-break:** claims submitted on the same day are processed in `claim_id` order (the data has no time of day).
- **Running totals for claims to check use our own predictions** of earlier claims, so one wrong prediction can carry forward. Past claims use the payer's real decision.
- **D10 is inferred, not documented.** PY03's handbook only says contract terms "may apply". The whole-hours rule and its 1 July 2026 start come from the dev data (June: all 50 such claims paid; from July: none paid). The remark text was used to discover it, never as an input.
- **Code order rests on small counts for some pairs.** PY03 reports D07/D08 ahead of D09 (4 of 4 dev claims), unlike PY01 and PY02. D05 against D03 and D09 has almost no evidence; 7 claims to check are affected, all predicted denied either way.
- **Corrected claims (frequency 7) are untested.** Past claims contain none, so the 14 in the claims to check follow the help article only and all go to review.
- **Claims to check run to February 2027**, beyond the past data. A bulletin issued after the data pack would be invisible.
- **Not built:** a "simulated" evaluation (using predictions instead of real outcomes for past claims), the learned model tier and the optional language-model wording. See `docs/TASKS.md`.

## Tools used
Claude Code (Anthropic) for planning, coding and analysis. Python libraries: pandas, scikit-learn (for the stratified split), PyYAML, pytest, Streamlit (demo screen). No language model is called when the checker runs. Working notes on how AI was used, including mistakes: `docs/ai_log.md`.

## Layout
- `PLANNING.md`, `docs/BUILD_SPEC.md`, `docs/TASKS.md`: scope, specification and build order
- `docs/payer_rules.md`: the payer rules distilled from the documents
- `docs/findings.md`: evidence from the dev split for every rule decision
- `docs/design.md`: system design and where it sits in the platform
- `src/claimcheck/`: code; `app/`: demo screen; `tests/`: tests; `outputs/`: predictions and metrics
