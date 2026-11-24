# AI log: how the build was done with Claude Code

Short notes on non-obvious choices, mistakes and user corrections. Feeds the presentation section "How you worked with AI".

## M0: Scaffold (2026-11-23)
- **Environment.** The machine has Python 3.14 and no packages, so a project-local `.venv/` was created (already in `.gitignore`) and the package installed with `pip install -e .`. Resolved versions: pandas 3.1.1, scikit-learn 1.9.1. pandas 3 is a major version with changed defaults (string dtype, copy-on-write), so M1 date and string cleaning must be tested, not assumed.
- **Raw-data integrity test.** Hashes of the 12 files in `1. RAW DATA/` are stored in `tests/raw_data_manifest.json` and compared on every `pytest` run; added or removed files also fail. `.DS_Store` is excluded because Finder rewrites it by itself, which would make the test fail for no real reason. The manifest must not be regenerated to make the test pass.
- **Extra module.** `integrity.py` is not in the BUILD_SPEC layout. It holds the hashing helper so the later "hash before/after a run" test (acceptance criterion 5) can reuse it.
- **Project root.** `paths.py` finds the root by walking up to the folder containing `1. RAW DATA` and raises if it is not found (`CLAIMCHECK_ROOT` overrides), in line with "no silent guessing".
- **Left alone.** `outputs/predictions.csv` (header-only placeholder) and `3. WORKING FOLDER/` were not touched. No git repository exists and none was created, since that was not asked for.

## M1: Clean and load data (2026-11-23)
- **Mistake: the virtualenv was created inside an iCloud-synced Desktop folder.** After M0, iCloud offloaded the venv's files, so `import pandas` hung for minutes (files flagged `dataless`). Diagnosed with `ls -lO`, then rebuilt the venv as `.venv.nosync/` (iCloud skips `*.nosync`) with a `.venv` symlink so the commands stay the same. Lesson: a hang is not always the code; check the environment first.
- **Mistake: told the user git had no identity configured.** I read a non-zero exit code from a chained command as "missing". It was set. Corrected in the next message.
- **Read every CSV as text first** (`dtype=str, keep_default_na=False`), so pandas cannot silently coerce a date, a blank or `' U1'`. Each column is then cleaned by one small pure function that raises `DataError` naming the column and the bad values.
- **Kept `None`, `datetime.date` and ints in `object` columns on purpose.** pandas 3 would turn a text column with `None` into its new `str` dtype with `NaN`, and rule code checking `modifier is None` would then be wrong. A test covers this.
- **US dates checked, not assumed:** the first part is never above 12 in 1,016 values, so month/day/year is safe.
- **`remark` is split off.** `load_claims` never returns it; `load_remarks()` is a separate, clearly labelled function for discovery only.
- **Payer aliases live in `data.py`, not `rules_config.yaml`.** They are a data-cleaning mapping, not a payer rule parameter. Flag for the user if they prefer them in config.
- **No tuning happened here:** profiling looked at formats and counts only, not at which claims were denied, so the dev/test split (M2) is not compromised.

## M2: Split (2026-11-24)
- **Split saved and reused.** `outputs/split.csv` (2,681 dev / 1,149 test) is written once; a rerun loads it. If the file no longer matches the history claims the loader raises, so the test set can never be reshuffled silently. A test checks the saved file equals the seed-42 split.
- **Row-order independent.** The history is sorted by `claim_id` before splitting, so the split does not depend on how the CSV was read.
- **Small test classes.** Test has only 8 D05, 10 D10 and 11 D04 claims, so per-code test metrics for these move in steps of about 10 points. Report counts next to percentages.
- **User asked mid-milestone for a time audit and an 80/20 partial build.** Finished M2 (already nearly done) and answered with the audit before starting anything else, since cutting scope changes `docs/TASKS.md` and needs the user's decision.

## Stage 1 of the 80/20 plan: stateless rules (2026-11-24)
- **Plan change agreed with the user.** The audit showed M3 to M5 were 100 of the remaining 160 budgeted minutes, while 80% of predictable denials need no timeline. `docs/TASKS.md` now has a staged plan; review points went from six to three.
- **Rules built straight from the documents, scored on dev, nothing tuned.** Result: 0 false alarms, 93.3% paid/denied accuracy. This is a useful check on the AI-written rule extraction: if a threshold or date had been misread, false alarms would show.
- **Did not fix the precedence yet, although the dev errors already show it is wrong.** Reordering before D02/D05/D06 exist would mean doing it twice; the evidence is recorded in `findings.md` for stage 3.
- **PY03 amendment-3 rule is in the config but switched off** (`enabled: false`), because its scope is unknown. Predicting it bluntly would trade missed D10s for false alarms on a rule not in any payer document.
- **Leak guard.** Claims are reduced to an allow-list of fields before any rule sees them, and a test uses a spy dict to prove no rule reads `remark`, `status` or `denial_code`.
- **Bug caught on first run:** a dataclass default shared one mutable `EvvDay` object; Python 3.14 rejects this. Switched to `default_factory`.
- **Dropped `explain.py`.** Each rule builds its own message and fix, since the LLM wording path is out of scope now.

## Stage 2: rules that depend on earlier claims (2026-11-24)
- **User corrected the communication style twice.** First: no technical terms at all. Then: that went too far; codes, statuses and error types are fine, only unexplained software jargon ("in config") is the problem. Lesson: ask what the reader already knows instead of assuming "non-technical" means everything.
- **Tested the assumptions instead of trusting them.** Three variants on dev: (A) one timeline of history + to-check claims, (B) history only, (C) denied claims also use up authorization units. A finds all 45 D02; B misses 8; C raises 36 false alarms. So the documented reading (A) is right, and the to-check claims really are interleaved with the history.
- **Authorization balance is not checked when the authorization does not fit the claim** (wrong patient, service or dates). The balance of the wrong authorization says nothing, and it would add noise to the precedence evidence.
- **Left one false alarm alone** (a paid claim we call D02). One case is not enough to change a rule.
- **Precedence evidence is now complete but the order is not changed yet**, to keep stage 2 a clean before/after of adding the three rules.
