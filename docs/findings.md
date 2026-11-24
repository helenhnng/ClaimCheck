# Findings: evidence from the data

Every rule ambiguity resolved on the **dev split** is recorded here with counts. Test-split numbers never drive a decision. `remark` is used for discovery only, never as a feature.

## Data quirks (M1)
Profiled on the full files (cleaning does not look at outcomes, so no split is needed). Reproduce with `python -m claimcheck.data` and `python notebooks/profile_raw.py`.

### Rows in and out
| Table | Rows in | Exact duplicate rows dropped | Rows out |
|---|---|---|---|
| `claims_history.csv` | 3,862 | 32 | 3,830 |
| `claims_to_check.csv` | 546 | 0 | 546 |
| `authorizations.csv` | 780 | 0 | 780 |
| `evv_visits.csv` | 5,076 | 0 | 5,076 |

No row is dropped for any other reason. After de-duplication `claim_id` is unique, and no `claim_id` is in both claim files.

### Mappings applied to claims (counts after de-duplication)
| Cleaning step | History | To-check |
|---|---|---|
| Payer name mapped to id (`NORTHWIND HP`, `Northwind Health Plan` → PY01; `Harbor Medicaid Plan`, `Harbor Medicaid` → PY02; `SUMMIT CARE`, `Summit Care Partners` → PY03) | 923 | 148 |
| `service_code` trailing space stripped | 175 | 34 |
| `modifier` stripped / upper-cased (` U1`, `U1 `, `u1`, …) | 133 | 10 |
| `date_of_service` in US format | 455 | 73 |
| `submitted_date` in US format | 419 | 63 |
| Blank `auth_id` (kept as `None`) | 84 | 9 |
| `frequency_code = 7` | 0 | 14 |

- **US dates are month/day/year.** In all 1,016 US-format values (raw files) the first part is never above 12, and the second part is above 12 in 606. So `07/09/2026` is 9 July.
- After cleaning: payers are only PY01/PY02/PY03, services only T1019/T1005/S5125, modifiers only U1/U2/U3 or none.
- `submitted_date` is never before `date_of_service` (lag 1 to 110 days in history, 1 to 129 in to-check).

### `authorizations.csv` and `evv_visits.csv`: clean
- **Authorizations:** payer ids already `PY0x`, no whitespace or case issues, all dates ISO, `auth_id` unique. Only two periods exist: 2026-06-01 to 2026-08-31 and 2026-09-01 to 2026-11-30 (390 each). Each patient has one payer.
- **EVV:** no whitespace or case issues, all timestamps `YYYY-MM-DD HH:MM`, `visit_id` unique, every `clock_out` is after `clock_in` (60 to 554 minutes). Status: 4,989 verified, 50 rejected, 37 manual_edit_pending. 191 visits cross midnight.

### Things to carry into later milestones
- **Every non-blank `auth_id` on a claim exists in `authorizations.csv`** (history and to-check). So D08 can never come from "auth not found" in this data; it must come from a payer/patient/service mismatch or the date window (M4).
- **All 14 corrected claims point at an `original_claim_id` in the history**, none at another to-check claim.
- **History date-of-service ends 2026-10-20; to-check runs to 2026-11-10.** Both sit inside the two authorization periods.
- **The 32 dropped rows are exact copies of another row** (same `claim_id`, same outcome), so they are export duplicates, not resubmissions, and do not count as duplicate claims for D05.

## Open questions from `docs/payer_rules.md` §5
Status of each: **open**, or **resolved** with the evidence.

| # | Question | Status | Evidence (dev counts) | Decision |
|---|---|---|---|---|
| 1 | Filing boundary (`>` vs `>=`) | resolved (stage 3) | Dev claims filed exactly on the limit day: 3 paid, 2 D02, 0 D03. One day over: 4 D03, 3 D09, 0 paid | Deny when days > limit |
| 2 | Duplicate scope (denied earlier claims, freq 7) | resolved for freq 1 (stage 2); freq 7 untestable | Key = payer + patient + service + DOS, any earlier claim whatever its outcome: fires on 20 dev claims, 19 coded D05, 1 coded D10 (also a duplicate). 0 true D05 missed, 0 fired on paid claims | Keep as documented. Freq 7 never a duplicate (from `billing_basics.md` only: history has no freq 7) |
| 3 | Partial auth exhaustion (whole claim denied; only paid claims draw down) | resolved (stage 2) | Paid-only drawdown: D02 fires on 60 dev claims, covers all 45 true D02, 1 fired on a paid claim. If denied claims also drew down: fires on 114, 36 of them paid claims | Whole claim denied when units > balance; only paid claims draw down |
| 4 | PY02 daily max (order applied, paid claims only) | resolved (stage 2) | Submission order, paid units only, all services: fires on 74 dev claims, covers all 55 true D06, 0 fired on paid claims (the other 19 carry a higher-ranked code) | Keep as documented |
| 5 | PY02 modifiers on non-T1019 services / pre-September U3 | resolved (stage 3) | D04 as documented: 26 of 26 dev D04 found, 0 fired on paid claims. PY02 S5125/T1005 never carry a modifier. T1019 with U3: 13 paid, 12 D04, split exactly by the weekend-from-1-Sep rule | Keep as documented; no extra modifier rule |
| 6 | PY01 `U1` modifier | resolved (stage 3) | PY01 T1019 with U1 and no other rule broken: 117 paid, 2 D99. Without a modifier: 122 paid, 7 D99. Same for PY03 | U1 is ignored outside PY02; no rule |
| 7 | PY03 contract amendment 3 scope (D10) | resolved (stage 3) | PY03 dev claims with non-whole-hour units and no other rule broken: DOS in June 50 paid, 0 denied; DOS from July 0 paid, 15 D10, 6 D99 (all with the amendment-3 remark). No agency or service pattern | D10 when `units % 4 != 0`, PY03, DOS >= 2026-07-01, all agencies |
| 8 | Precedence when several rules fire | resolved (stage 3), thin evidence for some pairs | See "Code order" below | Default D01, D09, D07, D08, D10, D05, D04, D06, D02, D03; PY03 puts D07, D08, D10 before D09 |
| 9 | Data quirks (payer names, date formats) | resolved (M1) | 6 payer aliases, 2 date formats, whitespace/case in `service_code` and `modifier`; see "Data quirks" | Explicit alias map, two explicit date formats (US = month/day/year), strip + upper-case codes; unknown values raise |
| 10 | Ordering on the to-check set | resolved (stage 2) | One timeline of history + to-check claims finds all 45 dev D02; history claims alone find 37 and miss 8. So the payer's balances already reflect to-check claims submitted earlier | Walk history and to-check together by `submitted_date`, then `claim_id`; history claims update the state with their real outcome, to-check claims with our prediction |

## Stage 1 baseline: six stateless rules, placeholder precedence (dev, 2,681 claims)
Rules D07, D08, D03, D01, D04, D09 exactly as documented, nothing tuned. Full report: `outputs/metrics_dev.md`.

| Measure | Dev |
|---|---|
| Paid/denied accuracy | 93.3% |
| Denied precision / recall | 100.0% / 76.6% |
| False alarms (predicted denied, was paid) | 0 |
| Missed denials | 180 |
| Exact-code accuracy | 91.1% (ceiling 98.1%: 51 D99) |

- **No false alarms.** Every one of the 589 claims flagged by a stateless rule was really denied, so the documented rules and the default choices (`>` filing boundary, sum-then-round) fit the dev data.
- **The 180 missed denials are the codes not built yet:** D06 55, D99 49, D02 40, D05 19, D10 17.
- **The placeholder precedence is wrong (evidence for question 8).** 61 dev claims were denied but given the wrong code. The pattern: when EVV is missing or short *and* another rule is broken, the payer reports the EVV code.

| Payer reported | We predicted | Dev claims |
|---|---|---|
| D09 | D03 | 18 |
| D01 | D03 | 10 |
| D10 | D09 | 8 |
| D02 | D03 | 5 |
| D01 | D07 | 4 |
| D09 | D07 | 4 |
| D09 | D08 | 4 |
| D01 | D08 | 3 |
| D99 | D09 | 2 |
| D09 | D04 | 1 |

  So D01 and D09 outrank D03, D07, D08 and D04, and D10 and D02 outrank at least D09 and D03. The order is fixed in stage 3, once D02, D05 and D06 exist.

## Stage 2: rules that depend on earlier claims (dev, 2,681 claims)
Added D05, D02 and D06 on a running timeline. Placeholder precedence still in place.

| Measure | Stage 1 | Stage 2 |
|---|---|---|
| Paid/denied accuracy | 93.3% | 97.6% |
| Denied precision / recall | 100.0% / 76.6% | 99.9% / 91.7% |
| False alarms | 0 | 1 |
| Missed denials | 180 | 64 (49 D99, 15 D10) |
| Exact-code accuracy | 91.1% | 95.2% (ceiling 98.1%) |
| Routed to review | 0.0% | 4.2% |

- **The one false alarm** (C012372, PY01): we compute 6 units left on AUTH11084 and the claim bills 8, yet it was paid. Not chased: a single case, and tuning to it would be fitting noise.
- **Every remaining missed denial is D99 (49) or D10 (15).** D99 is unpredictable; D10 is the PY03 amendment-3 rule, still switched off.

### Which code the payer reports when several rules are broken (dev claims with 2+ rules broken)
Rows are the set of rules we found broken; the columns show the code the payer reported.

| Rules broken | Payer reported | Dev claims |
|---|---|---|
| D03 + D09 | D09 | 17 |
| D03 + D01 | D01 | 9 |
| D09 + D06 | D09 | 7 |
| D09 + D02 | D09 (1 was D99) | 6 |
| D03 + D02 | D02 | 5 |
| D08 + D03 | D08 | 5 |
| D07 + D03 | D07 | 4 |
| D07 + D01 | D01 | 4 |
| D04 + D06 | D04 | 3 |
| D05 + D06 | D05 | 3 |
| D08 + D01 (one also D06) | D01 | 3 |
| D01 + D02, D01 + D06, D01 + D04 | D01 | 5 |
| D02 + D06 | D06 | 2 |
| D07 + D06 | D07 | 2 |
| D07 + D09 | D09 3, D07 2 | 5 |
| D08 + D09 | D09 3, D08 2 | 5 |
| three rules incl. D09 (with D03, D07/D08/D04, D02/D06) | D09 | 4 |

Reading: D01 wins every pairing (21 of 21). D09 beats D03, D02, D06 and D04. D07 and D08 beat D03 and D06. D06 beats D02, and D02 beats D03. **Unclear:** D09 against D07 or D08 splits 6 to 4. The order is set in stage 3.

## Stage 3: rule decisions on dev

| Change | Dev paid/denied accuracy | Dev exact-code accuracy |
|---|---|---|
| Stage 2 (placeholder code order, D10 off) | 97.6% | 95.2% |
| + code order from dev, D10 on from 2026-07-01 | 98.4% | 98.1% (the ceiling) |

- **Filing boundary:** `>` confirmed (question 1). No change.
- **EVV aggregation:** sum-then-round and round-then-sum give identical dev results (D09 fires on 181 claims, 0 paid, 0 true D09 missed either way). Kept sum-then-round, which is what `billing_basics.md` describes.
- **Modifiers:** no rule beyond PY02 T1019 (questions 5 and 6). No change.
- **PY03 amendment 3:** switched on with an effective date of 2026-07-01 (question 7). On dev it finds all 25 D10. It also fires on 8 claims the payer coded D99; all 8 carry the amendment-3 remark, so the cause is right and the payer's label is inconsistent.

### Code order
Pairwise results from dev claims that break two or more rules ("A > B: n" means the payer reported A on n claims that also broke B). No pair goes both ways once D10 has its start date.

- **PY01:** D01 > D03 8, D01 > D07 2, D01 > D08 2, D09 > D03 17, D09 > D07 3, D09 > D08 4, D09 > D02 2, D07 > D03 3, D08 > D03 4, D02 > D03 3.
- **PY02:** D01 > D06 3, D01 > D07 2, D01 > D08 1, D01 > D04 1, D09 > D06 8, D09 > D02 2, D09 > D04 1, D09 > D07 1, D04 > D06 3, D05 > D06 3, D07 > D06 2, D06 > D02 2.
- **PY03:** D01 > D10 3, D01 > D02 3, D01 > D03 2, D07 > D09 2, D08 > D09 2, D07 > D10 1, D10 > D09 8, D10 > D02 1, D10 > D05 1, D09 > D03 3, D09 > D02 3, D02 > D03 2, D07 > D03 1, D08 > D03 1.

Order chosen: **D01, D09, D07, D08, D10, D05, D04, D06, D02, D03**, with **PY03: D01, D07, D08, D10, D09, D05, D04, D06, D02, D03**.

- **PY03 differs:** it reports the authorization codes ahead of D09 (4 of 4), where PY01 and PY02 report D09 first (8 of 8).
- **Thin spots:** D05 is placed from two pairs only (D05 > D06, D10 > D05). D05 against D03 and D09 was never seen on dev. D01 against D07/D08 on PY03 was never seen (assumed the same as the other payers).

## Final test score (scored once, 2026-11-24)

| Measure | Dev (2,681) | Test (1,149) |
|---|---|---|
| Paid/denied accuracy | 98.4% | 98.4% |
| Denied precision / recall | 99.9% / 94.4% | 100.0% / 94.5% |
| False alarms | 1 | 0 |
| Missed denials | 43 (all D99) | 18 (all D99) |
| Exact-code accuracy | 98.1% | 98.0% |
| Ceiling (share that is not D99) | 98.1% | 98.1% |

Test errors: 18 D99 predicted paid, 4 D99 predicted D10, 1 D03 predicted D05. Dev and test agree, so the rules were not fitted to quirks of the dev claims.

## Rule decisions (M5)
_Superseded by "Stage 3: rule decisions on dev" above._

## Post-test changes
- **Review routing only (no status or code changed):** a paid PY02 claim near the 32-unit daily maximum was sent to review even when no earlier claim existed for that day, which is noise (24 of the 546 claims to check). Now it is flagged only when earlier paid units exist. Review rate on test went from 4.4% to 1.7%; every other test number is identical.
- **Seen on test, deliberately not acted on:** one test claim that broke both D03 and D05 was coded D03, where our order says D05. One claim is not enough to reorder, and changing a rule because of test would break the score-once discipline. Seven claims to check break D05 together with D03 or D09; all are predicted denied either way, only the code could differ.
