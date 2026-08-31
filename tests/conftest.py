"""Test-tier gate: hermetic tests everywhere, data-backed tests where the data is.

The suite has two tiers and they are not interchangeable.

**Hermetic** tests run from a clean checkout with synthetic or redistributable
fixtures. They need no network and no local downloads, and they are the tests a
stranger can run immediately after ``pip install -r requirements.lock.txt``.

**Data-backed** tests re-audit the real published workbooks, PDFs and the
Parquet tables built from them. Those inputs are third-party documents whose
redistribution terms are unresolved, plus generated tables that are deliberately
git-ignored, so a public release cannot ship them. Without them these tests
cannot run at all.

This hook skips the data-backed tests **only when the local inputs are actually
absent**, which it decides by looking at the filesystem rather than at a flag.
In a full working tree nothing is skipped and every test runs. In a release tree
the skipped tests are named, counted separately and reported with a reason —
a skipped audit is never folded into a passing hermetic total, because "did not
run" and "passed" are different facts and only one of them is evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).with_name("data_backed_tests.txt")

SKIP_REASON = (
    "data-backed: needs a local non-redistributable input (an official "
    "third-party download or a git-ignored generated table). Not run here, "
    "which is not the same as passing"
)


def local_inputs_present() -> bool:
    """Whether this checkout has the official downloads and generated tables.

    Measured from the filesystem. A test tier that could be switched on by an
    environment variable would eventually be switched on by accident.
    """
    raw = ROOT / "data" / "raw"
    features = ROOT / "data" / "features"
    has_raw = raw.is_dir() and any(
        path.is_dir() and path.name != "_manifests" for path in raw.iterdir()
    )
    has_features = features.is_dir() and any(features.glob("*.parquet"))
    return has_raw and has_features


def _registry() -> set:
    if not REGISTRY_PATH.is_file():
        return set()
    return {
        line.strip()
        for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def pytest_collection_modifyitems(config, items) -> None:
    if local_inputs_present():
        return
    registry = _registry()
    if not registry:
        return
    for item in items:
        if item.nodeid.replace("\\", "/") in registry:
            item.add_marker(pytest.mark.skip(reason=SKIP_REASON))
