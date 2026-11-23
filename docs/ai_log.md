# AI log: how the build was done with Claude Code

Short notes on non-obvious choices, mistakes and user corrections. Feeds the presentation section "How you worked with AI".

## M0: Scaffold (2026-11-23)
- **Environment.** The machine has Python 3.14 and no packages, so a project-local `.venv/` was created (already in `.gitignore`) and the package installed with `pip install -e .`. Resolved versions: pandas 3.1.1, scikit-learn 1.9.1. pandas 3 is a major version with changed defaults (string dtype, copy-on-write), so M1 date and string cleaning must be tested, not assumed.
- **Raw-data integrity test.** Hashes of the 12 files in `1. RAW DATA/` are stored in `tests/raw_data_manifest.json` and compared on every `pytest` run; added or removed files also fail. `.DS_Store` is excluded because Finder rewrites it by itself, which would make the test fail for no real reason. The manifest must not be regenerated to make the test pass.
- **Extra module.** `integrity.py` is not in the BUILD_SPEC layout. It holds the hashing helper so the later "hash before/after a run" test (acceptance criterion 5) can reuse it.
- **Project root.** `paths.py` finds the root by walking up to the folder containing `1. RAW DATA` and raises if it is not found (`CLAIMCHECK_ROOT` overrides), in line with "no silent guessing".
- **Left alone.** `outputs/predictions.csv` (header-only placeholder) and `3. WORKING FOLDER/` were not touched. No git repository exists and none was created, since that was not asked for.
