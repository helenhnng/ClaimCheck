# PLANNING: Exchange4Health claim approval/denial predictor

Source of truth: `2. INSTRUCTIONS/` (build brief + setup and guidance) and `1. RAW DATA/` (read-only, never edited).

> **Build handoff:** Claude Code should start from `CLAUDE.md`, then `docs/BUILD_SPEC.md` (what to build) and `docs/TASKS.md` (milestones M0 to M8).

## Goal
For each claim in `claims_to_check.csv`, predict whether the payer will **pay or deny** it and, if denied, **which denial code** (D01 to D10, D99) will be reported, with the reason and a suggested fix. Output: `predictions.csv` with `claim_id,status,denial_code`.

## 🔒 Locked scope and decisions (2026-11-23)
These are fixed for the build. Anything outside them goes under "Next steps", not into the code.

| Decision | Locked choice | Why |
|---|---|---|
| **Product** | A **pre-submission claim checker** ("assistant") for agency billing teams | The brief: read payer rules, check claims *before* submission, predict denials, suggest the fix |
| **Human in the loop** | The assistant **flags and recommends; the biller decides**. Nothing is edited or submitted automatically | High-stakes cash decisions; the brief asks for a human where stakes are high |
| **Escalation** | D99, D10 and low-confidence predictions are routed to "needs human review" | Honest about what rules can't decide |
| **Data** | Synthetic CSVs only, behind loader functions (`load_claims()`, `load_evv()`, `load_auths()`) | Loaders are the integration seam: CSVs today, platform DB in production |
| **Platform integration** | **Not built.** Shown only in the design sketch (sits between "visit verified" and "claim submitted") | The brief asks for a prototype on synthetic data |
| **Architecture** | Cascade: **rules first** (D01 to D09, from `docs/payer_rules.md`), then a **small model** for precedence and the leftovers, then the **LLM only for the residual** (D10/D99 explanation, fix wording) | Accurate, auditable, near-zero tokens per claim |
| **LLM use** | Offline rule extraction (done) + optional per-claim explanation with **Haiku 5.5**, only for flagged claims | Token cost scales with difficulty, not volume |
| **Demo UI** | Simple **Streamlit** page (fallback: clean CLI output). Per claim: verdict, code, rule broken + doc citation, suggested fix, review flag | Live demo on the day |
| **Evaluation** | Locked holdout on history (see "Validation strategy") + per-code metrics | Shows whether it works |

### Explicitly out of scope (mention as next steps)
Real-time APIs, login/roles, EDI 837/835 formats, clearinghouse submission, auto-correcting claims, payer-side analytics, scaling and deployment, rollout/change management (discuss live, don't build).

## Constraints from the brief
- Time budget: 2 to 4 hours. Quality of thinking beats completeness; a clear plan plus a partial build beats a rushed full one.
- Synthetic data only. No real personal or health data.
- API key lives in an environment variable (never in code or repo). Credit $40, expires 21 Dec. Sonnet 5.5 for most work, Opus 5.5 for hard design, Haiku 5.5 for any per-claim LLM calls.
- Tell them which tools were used (Claude Code, other AI tools, libraries).
- Deadline: deliverables due **6pm UK the evening before the assessment day**.

## Validation strategy (locked)
1. **Clean first.** Drop the 32 exact-duplicate rows (3,862 rows become 3,830 claims). Normalise dates and payer names.
2. **Rule state uses the full timeline.** Authorization drawdown (D02), daily max (D06) and duplicates (D05) depend on *earlier* claims. Compute them over history + to-check claims in submission order, never only within one split. Never use information dated after the claim's `submitted_date`.
3. **Split before tuning.** A 70/30 **dev/test** split of history claims, stratified by payer and outcome code. Fix the seed and save the split to `outputs/`.
   - *Why not purely by time:* the to-check claims (submitted Aug 2026 to Feb 2027) **overlap** the history period (Jun 2026 to Jan 2027), so the real task is interleaved, not "predict the future". Late submissions are also mostly D03 (denial rate climbs to 70%+ in Dec/Jan), so a pure time split gives a skewed test set.
   - *Robustness check:* also report results on a time split (submitted ≥ 2026-10-15 as test) to show the rules don't depend on the period.
4. **Tune only on dev.** Resolve rule ambiguities (filing boundary, precedence, PY01 U1, PY03 D10 patterns) using dev claims only.
5. **Score test once** at the end, and report what was learned. Don't keep tweaking against it.
6. **Watch small classes.** D05 (27), D10 (35) and D04 (37) have few examples. Report counts next to the metrics, and prefer interpretable rules over a model that memorises them.
7. **Metrics:** paid/denied accuracy, precision/recall on "denied", exact-code accuracy, per-code confusion matrix, and the % of claims routed to human review. A false "paid" (missed denial) costs more than a false alarm.
8. **Ablation:** rules only, then + model, then + LLM. Show accuracy and token cost for each tier.

## Roadmap (from the brief, section 7)

### 1. Frame the problem ✅ (locked above)
- Pre-submission checker for agency billers; success = catch denials before submission, with a correct code and an actionable fix.

### 2. Design the system
- `docs/design.md` + diagram: components, rules vs model vs LLM, data per claim, human-in-the-loop, where it would sit in the platform.

### 3. Build it
- Clean data, then loaders, then the rule engine (config from `docs/payer_rules.md`), then precedence/model, then fix suggestions, then `predictions.csv`, then the Streamlit view.

### 4. Check it works
- Validation strategy above + unit tests per rule in `tests/`.

## Working plan (suggested time split)
| Phase | Time | Output | Status |
|---|---|---|---|
| Read data pack and payer docs, profile data | 30 min | `docs/payer_rules.md`, summary tab | ✅ Done |
| Frame + design | 30 min | Locked scope (above), `docs/design.md`, diagram | Scope ✅ / design ⏳ |
| Data cleaning + loaders + split | 30 min | `src/claimcheck/` loaders, saved split | ⏳ |
| Rule engine + precedence | 60 min | Rules-only baseline on dev | ⏳ |
| Model/LLM residual + fixes | 30 min | Improved predictor | ⏳ |
| Evaluation + tests | 30 min | Metrics on test, `tests/` | ⏳ |
| Streamlit demo, README | 30 min | Demo + README | ⏳ |

## Open questions to resolve on the dev split
See `docs/payer_rules.md` §5. Key ones:
- Timely-filing boundary (≤ vs <).
- Code precedence when several rules are broken.
- PY01 `U1` modifier: ignored or an undocumented rule?
- PY03 contract-specific D10 patterns (by agency?).
- Duplicate logic vs frequency code 7 / `original_claim_id`.
- Authorization drawdown and PY02 daily-max ordering (paid claims only, in submission order).

## What each layer answers
| Layer | Example questions | How |
|---|---|---|
| **0. Data cleaning** (code) | Which payer is "NORTHWIND HP"? Is `' u2'` the same as `U2`? What date is `09/13/2026`? | Payer alias map, trim + upper-case codes/modifiers, parse mixed date formats, reject rows that fail to parse |
| **1. Rules engine** (code) | Is there a verified EVV visit? (D01) Do units exceed EVV time? (D09) Filed too late? (D03) PY02 T1019 missing U2/U3? (D04) Auth exhausted / daily max hit? (D02/D06) Duplicate? (D05) Auth missing or invalid? (D07/D08) | Joins to EVV/auth, date maths, payer rounding, running totals in submission order, config from `docs/payer_rules.md` |
| **2. Model** (learned, no tokens) | Several rules broken: which code wins? Do the documents match payer behaviour (PY01 U1, filing boundary)? How confident are we? | Learn precedence and calibrate on the dev split; output a probability used for review routing |
| **3. LLM** (Haiku, flagged claims only) | Explain this denial and the fix in plain English. Does a new bulletin change the rules? | Prompt with the fired rule, document citation and claim fields; offline rule extraction is reviewed by a human |
| **4. Human** | "Under review": what now? Fix, write off or appeal? | Biller judgement, contacting the payer |

## Edge cases and known limits
1. **PY03 D10 lives in the remarks, not the documents.** "Contract amendment 3: services must be billed in whole hours" (units must be a multiple of 4). Only ~47 of ~157 PY03 claims with non-whole hours carry this remark, so the rule probably has a start date, applies only to some agencies, or is hidden when another code wins. Investigate on the dev split, then encode it as a rule.
2. **The same cause is coded two ways.** 12 D99 denials carry the amendment-3 remark, so the payer sometimes uses D99 for a D10 cause. Treat as label noise and state it.
3. **~61 D99 denials are unpredictable** ("Denied - contact payer", "Under review"). This caps achievable accuracy; route such cases to a human and state the ceiling up front.
4. **Remarks leak the answer.** They only exist after the payer decides, and `claims_to_check` has none. Use them to discover rules, never as a model feature.
5. **Corrected claims (freq 7) are absent from history.** All history claims are freq 1, but 14 to-check claims are freq 7. Only the `billing_basics.md` rules cover them (not a duplicate, judged on their own merits); there's no data on how payers code a correction that still has the original fault.
6. **Running totals depend on our own predictions.** Auth drawdown (D02) and the PY02 daily max (D06) count paid claims only, so for to-check claims an earlier wrong guess carries through. Run in submission order using our own predictions, and flag claims near a limit as uncertain.
7. **To-check claims go beyond the history** (submitted up to Feb 2027; history ends Jan 2027). Bulletins or contract changes after the data pack are invisible. This is a production risk to mention, not something to build for.
8. **EVV timing.** 191 visits cross midnight and belong to the clock-in day. Same-day visits must be summed *before* rounding; test sum-then-round vs round-then-sum on dev.
9. **Pending EVV.** `manual_edit_pending` counts as unverified, but the better advice is "hold, don't submit yet" rather than "will be denied". Use this as a human-in-the-loop example in the demo.
10. **Boundary values.** Exactly day 30/45/60, the PY01 remainder of exactly 8 minutes, exactly 32 daily units. Write a unit test for each.

Items 1, 3 and 5 are worth raising in the presentation.

## Deliverables checklist
- [ ] Code (GitHub repo or zip)
- [ ] Short README: what it does, how to run, assumptions
- [ ] Design sketch (`docs/design.md` / diagram)
- [ ] `predictions.csv` (`claim_id,status,denial_code`)
- [ ] Optional: `CLAUDE.md` / Claude Code session history
- [ ] Note of tools used
- [ ] Laptop with demo running

## Presentation outline (about 10 min)
1. Approach: pre-submission checker for billers; why this slice; what was left out.
2. Design: cascade (rules, then model, then LLM, then human), trade-offs, where it would plug into the platform.
3. Build: live demo (Streamlit), test results, next steps.
4. Working with AI: where it helped, where it went wrong, how outputs were checked.
