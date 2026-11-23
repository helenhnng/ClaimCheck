# TASKS: build order for ClaimCheck

Do the milestones in order. At the end of each one: run `pytest`, write a short report (what was done, the numbers, surprises), append notes to `docs/ai_log.md`, then **stop and wait for the user**. The specs are in `docs/BUILD_SPEC.md`.

Time budget: about 3 hours in total. If you're running over, finish the current milestone cleanly and list the rest as next steps. Never leave a half-built one.

---

## M0: Scaffold (≈10 min)
- [ ] `pyproject.toml` (src layout, package `claimcheck`), update `requirements.txt` (pandas, numpy, scikit-learn, pyyaml, streamlit, pytest, anthropic).
- [ ] `paths.py` resolves the project root and the quoted folder names (`1. RAW DATA`, etc.).
- [ ] Create empty `docs/findings.md` and `docs/ai_log.md` with headings.
- [ ] Raw-data integrity test (hash the files in `1. RAW DATA/`; the test fails if anything changes).

**Done when:** `pip install -e . && pytest` runs green.

## M1: Clean and load data (≈25 min)
- [ ] `data.py` loaders with all cleaning from BUILD_SPEC §2 (payer map, strip/upper-case codes, mixed dates, drop exact duplicates).
- [ ] Profile `evv_visits.csv` and `authorizations.csv` for the same quirks; record them in `findings.md`.
- [ ] Tests: payer mapping (including an unknown value raising), modifier normalisation, both date formats, 3,862 → 3,830 rows.

**Report:** row counts in and out, every mapping applied, any surprises.

## M2: Split (≈10 min)
- [ ] `split.py` per BUILD_SPEC §5.9, writes `outputs/split.csv`.
- [ ] Tests: no id on both sides, ~70/30 sizes, stratum shares within ±2 pts, file reused on rerun.

**Report:** dev/test sizes and the payer × code table for each side.

## M3: EVV units + timeline state (≈30 min)
- [ ] `evv.py` (clock-in date, verified only, sum-then-round, payer rounding, pending flag).
- [ ] `timeline.py` sequential state (duplicate keys, auth balance, PY02 daily paid units) with `actual` and `simulated` modes.
- [ ] Tests: overnight visit, two same-day visits, PY01 7 vs 8 minute remainder, auth drawdown only on paid claims, freq 7 not a duplicate, a denied first claim still makes the second a duplicate.

## M4: Rules engine, rules only (≈40 min)
- [ ] `rules_config.yaml` ported from `docs/payer_rules.md` §3 + §6.
- [ ] `rules.py` with all 10 rules (BUILD_SPEC §5.5), returning every hit.
- [ ] Default precedence; first `predict.py` + `evaluate.py` run on **dev**.
- [ ] Boundary tests from BUILD_SPEC §6.6.

**Report:** dev status accuracy, exact-code accuracy, per-code recall. The largest error groups.

## M5: Resolve ambiguities on dev (≈30 min)
Work through `docs/payer_rules.md` §5 using **dev only**. For each, try the alternatives, keep the one that matches more dev claims, and record the evidence in `findings.md`:
- [ ] Filing boundary (`>` vs `>=`).
- [ ] Sum-then-round vs round-then-sum for EVV.
- [ ] PY01 `U1` and other modifier behaviour outside PY02 T1019.
- [ ] PY03 amendment-3 scope: effective date? which agencies? hidden by precedence? (You may read `remark` here, for discovery only.)
- [ ] Learned precedence (`learn_precedence`) replaces the default order.
- [ ] Update `rules_config.yaml` and `docs/payer_rules.md` together.

**Report:** before/after dev metrics for each change.

## M6: Explain, review routing, outputs (≈20 min)
- [ ] `explain.py` templates for every code (LLM path behind `--llm`, off by default).
- [ ] `review.py` rules (BUILD_SPEC §5.8) and the `action` column.
- [ ] `predict.py` writes both prediction files for `claims_to_check.csv`; schema test.

**Report:** counts by action; 5 sample rows from `predictions_detailed.csv`.

## M7: Final evaluation (≈15 min)
- [ ] Score **test once**: actual mode, simulated mode and the time split. Ablation table.
- [ ] D99 ceiling and review rate in `metrics_test.md`.
- [ ] Short failure analysis: the 3 biggest error groups and why.

**Report:** the headline table for the presentation. **Do not change the rules after this** (if something must change, record it as a post-test change in `findings.md`).

## M8: Demo + docs (≈25 min)
- [ ] `app/streamlit_app.py` per BUILD_SPEC §5.12.
- [ ] README: what it does, how to run, assumptions (tie-break order, mode, D99 never predicted, freq 7 untested), tools used.
- [ ] `docs/design.md` checked against what was built.

## Optional (only if time remains)
- [ ] Tier-2 model (shallow tree) if dev shows a gap that rules can't close; include it in the ablation.
- [ ] `--llm` explanations with Haiku for flagged claims, with the token count in the ablation.
- [ ] Patient-grouped split as a stricter robustness check.
