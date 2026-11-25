# ClaimCheck: pre-submission claim checker

Exchange4Health take-home. ClaimCheck reads a home-care agency's unsubmitted claims and, for each one, predicts whether the payer will **pay or deny** it and which **denial code** it will report. For every predicted denial it gives the **rule broken**, the **payer document** it comes from, a **suggested fix**, and an **action** for the biller: submit, fix then submit, hold, or review. The biller decides; nothing is changed or submitted automatically.

> **C019627, PY02, denied D08.** Authorization AUTH13917 is not valid for this claim: it runs 1 Jun 2026 to 31 Aug 2026, the date of service is 30 Sep 2026. *(PY02 Billing Guide, Authorizations)* **Fix:** Replace the authorization number. AUTH13920 is on file for this patient, service and date.

Design sketch: [`docs/design_sketch.jpg`](docs/design_sketch.jpg). Predictions: [`outputs/predictions.csv`](outputs/predictions.csv).

## Results
70% of past claims (dev) were used to build and check the rules. 30% (test) were held back and scored once.

| Measure | Dev (2,681) | Test (1,149) |
|---|---|---|
| Paid/denied accuracy | 98.4% | 98.4% |
| Denied precision / recall | 99.9% / 94.4% | 100.0% / 94.5% |
| False alarms (predicted denied, was paid) | 1 | 0 |
| Missed denials (predicted paid, was denied) | 43 | 18 |
| Exact-code accuracy (best possible 98.1%) | 98.1% | 98.0% |

- **Every missed denial is a D99** ("contact payer" / "under review"). No field in the data predicts it, so ClaimCheck never predicts it; that sets the 98.1% ceiling. Two standard machine-learning models asked to find the D99 claims scored no better than chance (AUC 0.46 and 0.47), which is why the checker uses rules only.
- **For the 546 claims to check:** 377 paid, 169 denied. Actions: 360 submit, 147 fix then submit, 35 review, 4 hold.

## How to run
Needs Python 3.11 or later (built and tested on 3.14). Run from this folder.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pytest
python -m claimcheck.predict
streamlit run app/streamlit_app.py
```

- `pytest` runs 158 automated checks (about 5 seconds).
- `python -m claimcheck.predict` rewrites `outputs/predictions.csv` and `outputs/predictions_detailed.csv`.
- The last command opens the demo screen at http://localhost:8501. Upload `1. RAW DATA/claims_to_check.csv`; the file is cleaned and checked on the spot, and nothing is pre-loaded.

No API key or internet connection is needed to run it: no AI model is called when a claim is checked. The raw data is never modified (a check compares a fingerprint of each file on every run).

## How it works
1. **Clean:** payer names, codes and two date formats are made consistent. Anything that cannot be read stops the run with a message; nothing is guessed.
2. **Timeline:** past claims and new claims are walked together in submission order, keeping running totals (claims already billed, units left on each authorization, paid units per patient per day).
3. **Rules:** ten checks, one per denial code. Every payer-specific number lives in one settings file (`src/claimcheck/rules_config.yaml`) with the dates it applies from, so a new payer bulletin is a reviewed settings change, not a code change.
4. **Code order:** when a claim breaks several rules the payer reports one code; the order was set from past claims that break two or more.
5. **Review routing:** decides what a person must look at.

| Code | Check |
|---|---|
| D01 | No verified EVV visit for the patient, service and date of service |
| D02 | Units exceed what is left on the authorization after earlier paid claims |
| D03 | Submitted after the filing limit (PY01 30 days, 45 from 1 Aug 2026; PY03 60; PY02 none) |
| D04 | PY02 T1019 without modifier U2 (weekends from 1 Sep 2026: U3) |
| D05 | Same payer, patient, service and date of service as an earlier claim |
| D06 | PY02: would take the patient's paid units for the day above 32 |
| D07 | No authorization number |
| D08 | Authorization is for another patient or service, or does not cover the date |
| D09 | Units exceed verified EVV time (PY01 8-minute rule; PY02 and PY03 complete units only) |
| D10 | PY03, date of service from 1 Jul 2026: units are not a whole number of hours |

## Assumptions and limits
- **Synthetic data.** The payers here follow their documents exactly. Real payers are messier, and a learned model that adds nothing here might earn its place on real data.
- **D10 is inferred, not documented.** PY03's handbook says only that contract terms "may apply". The whole-hours rule and its start date come from past claims (June: all 50 such claims paid; from July: none), so every predicted D10 goes to a person.
- **Corrected claims (frequency code 7) are untested.** Past claims contain none, so the 14 in the claims to check follow the help article and all go to review.
- **Same-day ordering:** claims submitted on the same day are processed in `claim_id` order, because the data has no time of day.
- **Running totals for new claims rely on our own predictions** of earlier new claims, so one wrong prediction can carry forward. Claims within 2 units of a limit are sent to review.
- **Some code-order pairs rest on two to four past examples.** Seven claims to check are affected; all are predicted denied either way, and only the code could differ.
- **Not built:** platform integration, auto-correction, and AI-written wording. The planning documents also describe a learned-model tier and extra evaluation modes that were cut for time and, for the model, because the evidence showed no gain.

## Tools used
Claude Code (Anthropic) for planning, coding and analysis. Python libraries: pandas, NumPy, scikit-learn (for the dev/test split and the D99 experiment), PyYAML, pytest, and Streamlit for the demo screen.

## What is in this folder
| Path | What it is |
|---|---|
| `src/claimcheck/` | The checker (cleaning, timeline, rules, settings file, prediction, scoring) |
| `app/streamlit_app.py` | The demo screen |
| `tests/` | Automated checks |
| `outputs/` | `predictions.csv`, a detailed version with reasons and fixes, and dev/test results |
| `1. RAW DATA/` | The data pack, unchanged |
| `docs/design_sketch.jpg`, `docs/design.md` | Design sketch and design notes |
| `docs/findings.md` | The evidence behind every rule decision |
| `docs/payer_rules.md` | The payer rules distilled from the documents |
| `docs/ai_log.md`, `CLAUDE.md` | How AI was used: running notes (including mistakes) and the instructions it worked under |
| `PLANNING.md`, `docs/BUILD_SPEC.md`, `docs/TASKS.md` | Planning documents, kept as written; where they differ from this README, the README describes what was built |
| `notebooks/` | Two one-off analysis scripts (data profile, D99 experiment) |
