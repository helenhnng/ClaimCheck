"""The raw data pack is read-only. These tests fail if any file in it changes.

The expected hashes live in ``tests/raw_data_manifest.json`` (recorded at M0).
Do not regenerate the manifest to make this test pass: a failure means the
source of truth was modified and must be restored.
"""
import json
from pathlib import Path

from claimcheck.integrity import hash_raw_data

MANIFEST = Path(__file__).parent / "raw_data_manifest.json"


def _expected() -> dict[str, str]:
    return json.loads(MANIFEST.read_text())


def test_manifest_covers_the_data_pack():
    expected = _expected()
    for name in (
        "claims_history.csv",
        "claims_to_check.csv",
        "authorizations.csv",
        "evv_visits.csv",
    ):
        assert name in expected
    assert any(name.startswith("payers/") for name in expected)


def test_no_raw_files_added_or_removed():
    assert sorted(hash_raw_data()) == sorted(_expected())


def test_raw_files_unchanged():
    actual = hash_raw_data()
    changed = [name for name, digest in _expected().items() if actual.get(name) != digest]
    assert not changed, f"Raw data files were modified: {changed}"
