# Findings: evidence from the data

Every rule ambiguity resolved on the **dev split** is recorded here with counts. Test-split numbers never drive a decision. `remark` is used for discovery only, never as a feature.

## Data quirks (M1)
_Row counts in/out, mappings applied, quirks found in `evv_visits.csv` and `authorizations.csv`._

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
| 9 | Data quirks (payer names, date formats) | open | | |
| 10 | Ordering on the to-check set | open | | |

## Rule decisions (M5)
_One entry per change: alternatives tried, dev metrics before/after, what was kept._

## Post-test changes
_Anything changed after the test split was scored (M7). Should stay empty._
