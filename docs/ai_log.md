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
