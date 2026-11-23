# BUILD_SPEC: ClaimCheck

What to build, how it fits together, and how we know it's done. Scope and rationale are in `PLANNING.md`; the domain rules are in `docs/payer_rules.md`.

---

## 1. Product in one paragraph
A biller loads the unsubmitted claims. For each claim, ClaimCheck predicts whether the payer will pay or deny it and which denial code it will report. It shows the rule broken with a citation to the payer document, gives a concrete fix, and flags the claims a human must look at. The biller decides what to do; nothing is changed or submitted automatically.

## 2. Inputs (read-only, in `1. RAW DATA/`)
| File | Rows | Notes |
|---|---|---|
| `claims_history.csv` | 3,862 (3,830 after removing 32 exact-duplicate rows) | Has `status`, `paid_amount`, `denial_code`, `remark`. All `frequency_code = 1`. |
| `claims_to_check.csv` | 546 | No outcome columns. 14 rows have `frequency_code = 7` (corrected claims). |
| `authorizations.csv` | 780 | `auth_id, patient_id, payer_id, service_code, start_date, end_date, units_authorized` |
| `evv_visits.csv` | 5,076 | `verification_status` ∈ {verified, rejected, manual_edit_pending}. 191 visits cross midnight. |
| `payers/*.md`, `billing_basics.md`, `denial_codes.md` | n/a | Already distilled into `docs/payer_rules.md` |

Claim columns: `claim_id, agency_id, payer, patient_id, service_code, date_of_service, submitted_date, units, auth_id, modifier, frequency_code, original_claim_id, billed_amount` (+ `status, paid_amount, denial_code, remark` in history).

### Known data quirks (must be handled in cleaning)
- **Payer names:** `PY01` = `NORTHWIND HP`, `Northwind Health Plan`; `PY02` = `Harbor Medicaid Plan`, `Harbor Medicaid`; `PY03` = `SUMMIT CARE`, `Summit Care Partners`. Map explicitly; raise on unknown values.
- **Codes with whitespace/case:** `service_code` has trailing spaces (`'T1019 '`); `modifier` has `' U1'`, `'U1 '`, `'u1'`, etc. Strip and upper-case. Empty → `None`.
- **Mixed date formats:** ISO `2026-06-09` and US `09/13/2026` in `date_of_service` and `submitted_date`. Parse both explicitly; raise on failure.
- **Exact duplicate rows** in history (32). Drop them, log the count.
- Check the same quirks in `evv_visits.csv` and `authorizations.csv` (dates, codes) and report what you find.

## 3. Architecture (cascade)
```
raw CSVs → [0 Clean/Load] → [Timeline] → [1 Rules engine] → [2 Precedence/Model] → [3 Explain (templates, optional LLM)] → [4 Review routing] → outputs + Streamlit
```
- Tier 0 and 1 are deterministic code.
- Tier 2 resolves which code wins when several rules fire, and gives a confidence.
- Tier 3 never changes the decision.
- Tier 4 decides what a human must see.

## 4. Package layout
```
pyproject.toml                 # package "claimcheck", src layout
requirements.txt
src/claimcheck/
  __init__.py
  paths.py                     # project-root-relative paths (folders contain spaces)
  rules_config.yaml            # all payer parameters with effective dates
  config.py                    # load + validate rules_config.yaml
  data.py                      # load_claims(kind), load_evv(), load_auths(); cleaning
  evv.py                       # verified minutes per (patient, service, date) + unit rounding
  timeline.py                  # merged, ordered timeline + sequential state (auth balance, daily paid units, duplicate keys)
  rules.py                     # one pure function per rule → RuleHit | None
  precedence.py                # code ordering (learned on dev) + optional small model
  explain.py                   # fix templates; optional LLM wording (Haiku, off by default)
  review.py                    # needs_review / hold logic
  split.py                     # dev/test split → outputs/split.csv
  predict.py                   # CLI: python -m claimcheck.predict
  evaluate.py                  # CLI: python -m claimcheck.evaluate
app/streamlit_app.py           # demo UI
tests/
docs/findings.md, docs/ai_log.md   # created during the build
outputs/                       # predictions.csv, predictions_detailed.csv, split.csv, metrics.md
```
Integration seam: `data.py` loaders are the only place that knows data comes from CSVs. In production they would read the platform database.

## 5. Module specs

### 5.1 `data.py`
- `load_claims(kind: Literal["history", "to_check"]) -> DataFrame` returns cleaned claims with: `payer_id`, normalised `service_code`/`modifier`, `date_of_service` and `submitted_date` as `datetime.date`, `units` int, `frequency_code` int, `source` = kind. History also keeps `status`, `denial_code`; `remark` is kept **only** in a separate column flagged as not-a-feature (or loaded via a separate function `load_remarks()`).
- `load_evv()`, `load_auths()` are cleaned the same way.
- Cleaning logs a summary: rows in/out, duplicates dropped, values mapped per column.

### 5.2 `evv.py`
- Visit date = **clock-in date**. Duration = clock_out − clock_in in minutes.
- Only `verified` visits count. Also expose whether a non-verified (`manual_edit_pending`/`rejected`) visit exists for the key (used for hold advice).
- **Sum minutes of all verified visits per (patient, service, date) first, then round** (default). Make the alternative (round each visit, then sum) a config switch so it can be tested on dev.
- Rounding per payer: `floor` → `m // 15`; `eight_minute_rule` → `m // 15 + (1 if m % 15 >= 8 else 0)`.

### 5.3 `rules_config.yaml`
Port `docs/payer_rules.md` §3 and §6. Every time-dependent parameter has `dos_from`/`dos_to`. Mark unresolved items with `# TBC` and default values. Include:
- Timely filing: PY01 30 days (DOS < 2026-08-01) / 45 days (DOS ≥ 2026-08-01); PY02 none; PY03 60 days. Boundary operator configurable (`>` default: deny if days > limit).
- PY02 modifier: T1019 needs `U2`; from DOS 2026-09-01 Sat/Sun T1019 needs `U3`.
- PY02 daily max: 32 units per patient per DOS, all services, counting paid claims only.
- PY03 contract amendment 3: `units % 4 != 0` → D10; `effective_from` and `agencies` TBC.
- Rounding per payer; EVV valid statuses; duplicate key.

### 5.4 `timeline.py`
Some rules depend on earlier claims, so prediction is a **sequential simulation**:
1. Merge history + to_check into one timeline sorted by `submitted_date`, then `claim_id` (tie-break; document this assumption).
2. Walk the timeline. For each claim, evaluate the rules using the **current state**, then update state:
   - **Duplicate keys seen:** `(payer_id, patient_id, service_code, date_of_service)`. Every submitted claim adds its key regardless of outcome. A `frequency_code = 1` claim whose key was already seen → D05. `frequency_code = 7` is never a duplicate.
   - **Auth balance:** `units_authorized − Σ units of earlier paid claims on that auth_id`. Only paid claims draw down.
   - **Daily paid units (PY02):** Σ units of earlier paid claims for that patient + DOS, across services.
3. "Paid" for state purposes depends on **mode**:
   - `actual`: history claims use their real `status`; to_check claims use their predicted status. This is the default for producing `predictions.csv`.
   - `simulated`: every claim (history included) uses its *predicted* status. Used in evaluation to measure error carrying through to later claims.
4. Expose the state numbers on each row (`auth_remaining_before`, `daily_paid_before`, `dup_of_claim_id`) for explanations and review routing.

### 5.5 `rules.py`
One pure function per rule: `check_xxx(claim, ctx, cfg) -> RuleHit | None`, where `RuleHit = (rule_id, denial_code, message, citation, fix, details)`.

| rule_id | Code | Logic |
|---|---|---|
| `auth_missing` | D07 | `auth_id` is empty |
| `auth_invalid` | D08 | auth not found, or payer/patient/service differ, or DOS outside `[start_date, end_date]` |
| `duplicate` | D05 | see timeline |
| `timely_filing` | D03 | `(submitted_date − DOS).days` exceeds the payer limit for that DOS |
| `evv_missing` | D01 | no verified minutes for (patient, service, DOS) |
| `modifier` | D04 | PY02 T1019 modifier ≠ required (U2/U3). Other payers: none unless dev evidence says otherwise |
| `evv_units` | D09 | `units > evv_units` (payer rounding). Skip if `evv_missing` fired |
| `auth_units` | D02 | `units > auth_remaining_before` (whole claim denied) |
| `daily_max` | D06 | PY02: `daily_paid_before + units > 32` |
| `contract_whole_hours` | D10 | PY03: `units % 4 != 0` (subject to TBC scope) |

Return **all** hits; precedence picks one. `citation` examples: `"PY02 Provider Notice 2026-08"`, `"PY01 Manual §6.1 + Bulletin 2026-07"`, `"billing_basics.md"`.

### 5.6 `precedence.py`
- Default order (a placeholder, to be **replaced by evidence from dev**): `D07, D08, D05, D03, D01, D04, D09, D02, D06, D10`.
- `learn_precedence(dev_df)` looks at dev claims with ≥ 2 hits and counts which code the payer reported. It derives an order (pairwise wins), writes it to `outputs/precedence.json` and reports conflicts.
- Optional tier-2 model (only if rules + precedence leave a meaningful gap on dev): a shallow decision tree or logistic regression on rule flags + payer + service, giving `p_denied` and the code. Must stay interpretable. Report its gain in the ablation.
- Confidence: `high` if exactly one hit or none with clean data; `medium` if several hits or near a limit; `low` if data was missing or ambiguous.

### 5.7 `explain.py`
- Deterministic fix template per rule (default, zero tokens), for example:
  - D04: "Add modifier U3 (weekend T1019 for Harbor from 1 Sep 2026)."
  - D03: "Past the 45-day filing limit by N days; consider a write-off or appeal."
  - D02: "Only R units remain on AUTHx; bill R units or request an authorization extension."
  - D09: "EVV supports E units; reduce to E or correct the EVV record."
- Optional `--llm`: for flagged claims only, call **Haiku 5.5** (model ID in config; check the exact string in Anthropic docs). Send the claim fields, the hit(s) and the cited rule text. Ask for JSON `{explanation, fix}`. Validate it; on failure fall back to the template. Cache by `(claim_id, hit set)` in `outputs/llm_cache.json`. Log tokens used. Payer rule text goes first in the prompt so it can be cached.

### 5.8 `review.py`
`needs_review = True` and a `review_reason` if any of these apply:
- the predicted code is D10, or the model/precedence confidence is `low`;
- the claim is a corrected claim (`frequency_code = 7`): no history examples exist;
- the claim is within 2 units of the auth balance or the PY02 daily max (it depends on predictions of earlier claims);
- only non-verified EVV exists (`manual_edit_pending`). Here the advice is **"Hold: EVV pending"**, not "will be denied".

D99 is never predicted (it can't be predicted); state this as a known limit.

### 5.9 `split.py`
- Uses cleaned, de-duplicated history (3,830). `stratum = payer_id + "_" + (denial_code or "PAID")`. `train_test_split(test_size=0.30, stratify=stratum, random_state=42)`.
- Writes `outputs/split.csv` (`claim_id,split`). If the file exists, **load it, don't regenerate** (unless `--force`).
- Secondary split: `time_split = "dev" if submitted_date < 2026-10-15 else "test"`.
- The split is applied **after** the timeline is built (state uses all claims).

### 5.10 `predict.py` (CLI)
`python -m claimcheck.predict [--mode actual|simulated] [--llm]`
- `outputs/predictions.csv`: exactly `claim_id,status,denial_code`. 546 rows, unique ids, `status ∈ {paid, denied}`, `denial_code` blank iff paid.
- `outputs/predictions_detailed.csv`: plus `payer_id, all_hits, rule_id, message, citation, fix, confidence, needs_review, review_reason, action` (`submit` / `fix_then_submit` / `hold` / `review`).

### 5.11 `evaluate.py` (CLI)
`python -m claimcheck.evaluate [--split dev|test] [--time-split] [--mode actual|simulated]`, writes `outputs/metrics_<split>.md`:
- Paid/denied accuracy; precision and recall on *denied*; exact-code accuracy (paid counts as a code).
- Per-code precision/recall with support counts; confusion matrix.
- Share routed to review.
- **Ceiling note:** count of D99 claims in the split (unpredictable).
- **Ablation:** rules with the default order → + learned precedence → + model (if built) → + LLM (token count only; it doesn't change decisions).
- A `mistakes` CSV of the top error groups (true vs predicted code) for the dev split only.

### 5.12 `app/streamlit_app.py`
`streamlit run app/streamlit_app.py`. Reads the `outputs/` files (it does not recompute unless a button is pressed).
- **Summary:** counts by action, predicted denials by code, payer filter.
- **Claim table:** filter by action, payer, code, needs_review.
- **Claim detail:** claim fields, verdict, code + meaning, rule + citation, fix, review reason, plus the EVV visits and authorization behind it.
- **Model health tab:** metrics from `outputs/metrics_test.md`.

## 6. Acceptance criteria (definition of done)
1. `pip install -e . && pytest` passes.
2. `python -m claimcheck.predict` produces valid `outputs/predictions.csv` (546 rows; schema as in 5.10).
3. `python -m claimcheck.evaluate --split test` produces metrics including per-code results and the D99 ceiling.
4. A test asserts that `remark` is not used by any rule or model input.
5. A test asserts the raw data files are unchanged (hash before/after a run).
6. Boundary tests exist: filing days exactly at 30/45/60 (and over by one), PY01 remainder 7 vs 8 minutes, PY02 daily total exactly 32 vs 33, Saturday T1019 on 2026-08-31 vs 2026-09-05, overnight visit dated to clock-in, two same-day visits summed before rounding, freq 7 not a duplicate.
7. The Streamlit app runs and shows a claim's detail with a citation and a fix.
8. `docs/findings.md` records every open question from `payer_rules.md` §5 as resolved (with evidence) or still open.
9. README updated: what it does, how to run, assumptions, tools used.
