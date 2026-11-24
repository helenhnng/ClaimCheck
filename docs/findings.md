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
| 1 | Filing boundary (`>` vs `>=`) | open | | |
| 2 | Duplicate scope (denied earlier claims, freq 7) | open | | |
| 3 | Partial auth exhaustion (whole claim denied; only paid claims draw down) | open | | |
| 4 | PY02 daily max (order applied, paid claims only) | open | | |
| 5 | PY02 modifiers on non-T1019 services / pre-September U3 | open | | |
| 6 | PY01 `U1` modifier | open | | |
| 7 | PY03 contract amendment 3 scope (D10) | open | | |
| 8 | Precedence when several rules fire | open | | |
| 9 | Data quirks (payer names, date formats) | resolved (M1) | 6 payer aliases, 2 date formats, whitespace/case in `service_code` and `modifier`; see "Data quirks" | Explicit alias map, two explicit date formats (US = month/day/year), strip + upper-case codes; unknown values raise |
| 10 | Ordering on the to-check set | open | | |

## Rule decisions (M5)
_One entry per change: alternatives tried, dev metrics before/after, what was kept._

## Post-test changes
_Anything changed after the test split was scored (M7). Should stay empty._
