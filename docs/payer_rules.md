# Payer rules (extracted from the documents)

Sources: `1. RAW DATA/payers/*.md`, `billing_basics.md`, `denial_codes.md`. These rules come from the documents only and have **not yet been checked against `claims_history.csv`**. Section 5 lists what the history needs to confirm.

Payers: **PY01** Northwind Health Plan · **PY02** Harbor Medicaid Plan · **PY03** Summit Care Partners.
Services: T1019 personal care · T1005 respite · S5125 attendant care. 1 unit = 15 minutes.

---

## 1. Rules that apply to all payers (from `billing_basics.md`)

| # | Rule | Denial code |
|---|---|---|
| G1 | Only EVV visits with `verification_status = verified` count. `manual_edit_pending` and `rejected` do **not**. | D01 |
| G2 | A visit belongs to the **clock-in date**, even when it runs past midnight. | D01 / D09 |
| G3 | If the same patient has more than one visit for the same service on the same day, the visits are **summed**. | D09 |
| G4 | The authorization must match the patient and the service, and be in force on the date of service. | D08 |
| G5 | Each **paid** claim draws units down from its authorization, **in submission order**. Once units run out, further claims are denied. | D02 |
| G6 | A corrected claim uses `frequency_code = 7` and gives the `original_claim_id`. It is processed on its own merits and is **not** a duplicate. | n/a |
| G7 | A new claim (`frequency_code = 1`) with the same **payer + patient + service + date of service** as a claim already submitted is a **duplicate**, *whatever happened to the first claim*. | D05 |
| G8 | Rounding minutes to units differs by payer (see section 2). | D09 |
| G9 | When a claim breaks more than one rule, the payer reports **only one code**. The precedence is not documented. | n/a |

---

## 2. Rule matrix by payer

| Rule | PY01 Northwind | PY02 Harbor | PY03 Summit |
|---|---|---|---|
| **Verified EVV required** (D01) | Yes, for T1019, T1005, S5125 (§4.2) | Yes (Visit verification) | Yes (§9.1) |
| **Unit rounding** (D09) | **8-minute rule**: `floor(min/15)`, plus 1 if the remainder is ≥ 8 min (§4.3) | **Floor**: complete 15-min units only | **Floor**: partial units not billable (§9.1) |
| **Units > EVV-verified time** (D09) | Denied | Denied (implied by "only complete increments may be billed") | Denied |
| **Auth number required** (D07) | Yes, on every claim (§4.5) | Yes, must reference the current auth | Yes, mandatory (§9.2) |
| **Auth matches patient/service/date** (D08) | Yes | Yes ("current" auth) | Yes |
| **Units exceed remaining auth** (D02) | Denied | Denied; units drawn down as claims are paid | Denied; paid units deducted |
| **Timely filing** (D03) | DOS < 2026-08-01: **30 days**<br>DOS ≥ 2026-08-01: **45 days** (Bulletin 2026-07) | **None** for in-state HCBS | **60 days** (§9.3) |
| **Modifier** (D04) | None documented | T1019 must have **U2**.<br>From DOS ≥ 2026-09-01: weekend (Sat/Sun) T1019 must have **U3**, weekday stays U2 (Notice 2026-08) | None documented |
| **Daily maximum** (D06) | None documented | **32 units per member per day**, across *all* HCBS services combined, counting only the **paid** total | None documented |
| **Duplicates** (D05) | Denied (§6.4) | Denied | Denied (§9.4) |
| **Contract-specific** (D10) | n/a | n/a | "Additional billing requirements may apply under your agency's contract" (§9.5). **Not documented**, so they must be inferred from history. |

---

## 3. Executable form (draft rule config)

```yaml
PY01:
  evv_required: true
  rounding: eight_minute_rule      # units = m//15 + (1 if m%15 >= 8 else 0)
  auth_required: true
  timely_filing:
    - {dos_from: null,       dos_to: 2026-07-31, days: 30}
    - {dos_from: 2026-08-01, dos_to: null,       days: 45}
  modifier_rules: []
  daily_max_units: null
PY02:
  evv_required: true
  rounding: floor
  auth_required: true
  timely_filing: null
  modifier_rules:
    - {service: T1019, dos_to: 2026-08-31, required: U2}
    - {service: T1019, dos_from: 2026-09-01, weekday: true,  required: U2}
    - {service: T1019, dos_from: 2026-09-01, weekend: true,  required: U3}
  daily_max_units: {limit: 32, scope: all_services, basis: paid_total}
PY03:
  evv_required: true
  rounding: floor
  auth_required: true
  timely_filing: [{days: 60}]
  modifier_rules: []
  daily_max_units: null
  contract_rules: learn_from_history   # D10, probably by agency_id
ALL:
  duplicate_key: [payer, patient_id, service_code, date_of_service]
  duplicate_applies_to_frequency: "1"
  auth_drawdown: paid_claims_in_submission_order
  evv_valid_status: [verified]
  evv_date_basis: clock_in
```

---

## 4. Rule to denial code mapping

| Check | Code |
|---|---|
| No verified EVV for patient + service + DOS | D01 |
| Units exceed remaining auth balance | D02 |
| `submitted_date − DOS` > payer limit | D03 |
| Missing or wrong modifier (PY02 T1019) | D04 |
| Duplicate (freq 1, same key as an earlier claim) | D05 |
| Daily paid total > 32 units (PY02) | D06 |
| `auth_id` blank | D07 |
| Auth id not found, or wrong patient, service or dates | D08 |
| Billed units > units supported by EVV time (payer rounding) | D09 |
| Contract-specific (PY03) | D10 |
| Anything else / manual review | D99 |

---

## 5. Ambiguities and open questions to check against history

1. **Filing boundary.** Is "within 30 days" `≤ 30` or `< 30`? Is it measured to `submitted_date`? Test both on the history.
2. **Duplicate scope.** Do voided or denied earlier claims still trigger D05? G7 says yes ("whatever happened"). Does a freq-7 claim with a missing or invalid `original_claim_id` get treated as a duplicate?
3. **Partial auth exhaustion.** If a claim needs 10 units and 6 remain, is the **whole claim** denied? The wording suggests yes. Do denied claims leave the balance untouched? (Only *paid* claims draw down.)
4. **PY02 daily max.** Which order is it applied in (submission order vs DOS)? Does it count only paid claims, as written?
5. **PY02 modifiers on non-T1019 services.** Does an extra or unexpected modifier cause a denial? Do weekend claims before 1 Sept with U3 count as wrong?
6. **PY01 modifiers.** The history shows PY01 claims carrying `U1` although the manual documents no modifier rule. Is it ignored, or is there an undocumented rule?
7. **PY03 contract rules (D10).** Undocumented in the manual, but **partly found in the history remarks** (see section 6).
8. **Precedence (G9).** Derive the order in which codes win from claims in history that break more than one rule.
9. **Data quirks.** Payer names in claims may not be clean `PY0x` ids, and there are mixed date formats (ISO vs `MM/DD/YYYY`). Normalise these before applying any rule.
10. **Ordering on the to-check set.** Auth drawdown, daily max and duplicate checks for `claims_to_check.csv` must take account of the history claims *and* earlier to-check claims, in submission order.

---

### Status after checking on the dev split (evidence in `docs/findings.md`)
- **2 Duplicate scope:** confirmed for frequency 1 (an earlier denied claim still makes a duplicate). Frequency 7 cannot be checked: history has none.
- **3 Partial auth exhaustion:** confirmed. The whole claim is denied; only paid claims draw down.
- **4 PY02 daily max:** confirmed. Submission order, paid units only, all services.
- **9 Data quirks:** resolved in cleaning.
- **10 Ordering:** confirmed. History and to-check claims form one timeline.
- **1, 5, 6, 7, 8:** still open.

---

## 6. Findings from the claims history (remarks)

> Source: `remark` column of `claims_history.csv` (after removing duplicates). Remarks are written **after** the payer decides, so they help discover rules but must **never** be used as a model input (`claims_to_check.csv` has no remarks).

### PY03 Summit: Contract amendment 3 (D10)
- **Remarks:** "Contract amendment 3: services must be billed in whole hours" / "Units not billable per amendment 3 (hourly increments)".
- **Likely rule:** for PY03, `units % 4 != 0` (not a whole number of hours) is denied as **D10**.
- **Coverage:** all 35 D10 denials are PY03 and carry one of these remarks.
- **Not yet explained:** only ~47 of ~157 PY03 claims with non-whole-hour units carry the remark. Candidates: an effective date (earliest remark is DOS 2026-07-01), only some agencies (AG008 has none), or the code is hidden when another denial takes priority. Resolve on the dev split.
- **Label noise:** 12 claims coded **D99** carry the same amendment-3 remark, so the payer sometimes reports this cause as D99.

```yaml
PY03:
  contract_rules:
    - id: amendment_3_whole_hours
      check: units % 4 == 0
      denial_code: D10
      effective_from: TBC   # earliest remark DOS 2026-07-01, to be confirmed
      agencies: TBC         # all, or a subset, to be confirmed
```

### D99 (other / manual review)
- About 61 of 73 D99 remarks are uninformative ("Denied - contact payer" 32, "Under review - see payer correspondence" 29). These cannot be predicted from the data and are routed to a human.
- The remaining 12 are the amendment-3 cases above.
