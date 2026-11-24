# CLAUDE.md: ClaimCheck (Exchange4Health take-home)

You are building **ClaimCheck**, a pre-submission claim checker for home-care agency billing teams. For each unsubmitted claim it predicts **paid or denied**, the **denial code** (D01 to D10, D99), the **rule broken** (with a citation to the payer document), a **suggested fix**, and whether a **human must review** it.

## Read these first (in this order)
1. `PLANNING.md`: locked scope, validation strategy, edge cases. **Locked decisions are not up for change**; if you think one is wrong, stop and ask.
2. `docs/BUILD_SPEC.md`: what to build: modules, interfaces, rule logic, outputs, acceptance criteria.
3. `docs/TASKS.md`: the build order. Work one milestone at a time.
4. `docs/payer_rules.md`: the payer rules (the domain source of truth after the raw documents).
5. `docs/design.md`: architecture and human-in-the-loop design.

## Hard rules
- **Never modify** `1. RAW DATA/` or `2. INSTRUCTIONS/`. Read only. They are the source of truth.
- **Never modify** `3. WORKING FOLDER/` unless the user explicitly asks.
- **Never use the `remark` column as a feature.** It is written after the payer decides and `claims_to_check.csv` has none. It may be used only to *discover* rules during investigation, on the dev split.
- **Never tune on the test split.** All rule investigation, threshold choices and precedence learning use `split == "dev"` only. Test is scored once per milestone report, not iterated against.
- **The LLM never decides a status or code.** Rules and the model decide; the LLM only explains and words fixes. It is off by default.
- **API keys only from environment variables** (`ANTHROPIC_API_KEY`). Never write a key into code, config, logs or git.
- **No silent guessing on data.** If a date, payer or code can't be parsed or mapped, raise or log it explicitly. Don't drop rows quietly.

## Conventions
- Python 3.11+, `pandas`, `scikit-learn`, `pyyaml`, `streamlit`, `pytest`, `anthropic` (optional).
- Code in `src/claimcheck/` (installable via `pyproject.toml`, `pip install -e .`). Tests in `tests/`. Generated files in `outputs/` only.
- Payer rule parameters live in `src/claimcheck/rules_config.yaml`, **not** hard-coded in Python. Rule logic in Python reads from config.
- Every rule hit carries `rule_id`, `denial_code`, `message`, `citation` (document + section) and `fix`.
- Keep functions small and pure where possible so each rule is unit-testable with a hand-built claim.
- Seeds fixed (`random_state=42`). Paths resolved relative to the project root, which contains folder names with spaces; always quote paths.

## How to work
- Do one milestone from `docs/TASKS.md` at a time. At the end of each: run `pytest`, report what was done, the numbers, and anything surprising, then **stop and wait** for the user. (From 2026-11-24 the unit is a **stage** of the 80/20 plan at the top of `docs/TASKS.md`.)
- When a rule ambiguity is resolved on the dev split, record the evidence (counts) in `docs/findings.md` and update `docs/payer_rules.md` + `rules_config.yaml` together.
- Append short notes to `docs/ai_log.md` when you make a non-obvious choice, hit a mistake, or the user corrects you. This feeds the presentation section "How you worked with AI".
- Prefer simple and explainable over clever. The time budget is 2 to 4 hours in total.
- Use Sonnet 5.5 for normal work. No per-claim LLM calls unless the user turns on `--llm`.
