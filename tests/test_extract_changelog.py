import importlib.util
from pathlib import Path

import pytest


def _module():
    spec = importlib.util.spec_from_file_location(
        "extract_changelog", Path("scripts/extract_changelog.py")
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_release_notes_for_exact_version():
    module = _module()
    changelog = """# Changelog

## [0.1.1] - 2026-06-24

Launch polish.

## [0.1.0] - 2026-06-24

Initial release.
"""
    assert module.extract_release_notes(changelog, "0.1.1") == "Launch polish.\n"
    assert module.extract_release_notes(changelog, "v0.1.0") == "Initial release.\n"


def test_extract_release_notes_fails_for_missing_version():
    module = _module()
    with pytest.raises(ValueError, match="no section"):
        module.extract_release_notes("# Changelog\n", "0.2.0")


def test_extract_release_notes_fails_for_empty_or_placeholder_section():
    module = _module()
    with pytest.raises(ValueError, match="empty"):
        module.extract_release_notes("# Changelog\n\n## [0.1.1] - 2026-06-24\n", "0.1.1")
    with pytest.raises(ValueError, match="placeholder"):
        module.extract_release_notes(
            "# Changelog\n\n## [0.1.1] - 2026-06-24\n\nTBD\n", "0.1.1"
        )
