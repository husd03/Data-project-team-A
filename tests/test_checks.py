"""
Unit tests for agent/checks.py — the friendly pre-flight error messages.

Run with:
    python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.checks import (
    SetupError,
    check_dependencies,
    check_data_files,
    check_excel_readable,
)


# ── check_dependencies ─────────────────────────────────────────────────────

def test_check_dependencies_passes_when_packages_installed():
    """pandas, numpy, openpyxl are installed in the test environment - should not raise."""
    check_dependencies()  # no exception = pass


def test_check_dependencies_error_message_mentions_instalation_bat():
    """If a package were missing, the message must point to instalation.bat."""
    import agent.checks as checks_module

    original = checks_module.REQUIRED_PACKAGES
    try:
        checks_module.REQUIRED_PACKAGES = [("definitely_not_a_real_package_xyz", "fake-package")]
        with pytest.raises(SetupError) as exc_info:
            checks_module.check_dependencies()
        msg = str(exc_info.value)
        assert "instalation.bat" in msg
        assert "fake-package" in msg
    finally:
        checks_module.REQUIRED_PACKAGES = original


# ── check_data_files ─────────────────────────────────────────────────────

def test_check_data_files_passes_when_all_exist(tmp_path):
    f1 = tmp_path / "a.xlsx"
    f2 = tmp_path / "b.xlsx"
    f3 = tmp_path / "c.xlsx"
    for f in (f1, f2, f3):
        f.write_bytes(b"not empty")

    check_data_files(str(f1), str(f2), str(f3))  # no exception = pass


def test_check_data_files_raises_when_missing(tmp_path):
    f1 = tmp_path / "a.xlsx"
    f1.write_bytes(b"not empty")
    missing_path = str(tmp_path / "does_not_exist.xlsx")

    with pytest.raises(SetupError) as exc_info:
        check_data_files(str(f1), missing_path, missing_path)

    msg = str(exc_info.value)
    assert "data/" in msg  # solution mentions the data/ folder
    assert missing_path in msg


def test_check_data_files_raises_when_empty(tmp_path):
    f1 = tmp_path / "a.xlsx"
    f2 = tmp_path / "b.xlsx"
    f3 = tmp_path / "c.xlsx"
    f1.write_bytes(b"")  # empty file
    f2.write_bytes(b"not empty")
    f3.write_bytes(b"not empty")

    with pytest.raises(SetupError) as exc_info:
        check_data_files(str(f1), str(f2), str(f3))

    msg = str(exc_info.value)
    assert "prázdné" in msg
    assert str(f1) in msg


# ── check_excel_readable ───────────────────────────────────────────────────

def test_check_excel_readable_passes_for_valid_excel(tmp_path):
    paths = []
    for name in ("a.xlsx", "b.xlsx", "c.xlsx"):
        p = tmp_path / name
        pd.DataFrame({"ID": [1, 2]}).to_excel(p, index=False)
        paths.append(str(p))

    check_excel_readable(*paths)  # no exception = pass


def test_check_excel_readable_raises_for_invalid_file(tmp_path):
    bad = tmp_path / "not_excel.xlsx"
    bad.write_text("this is just text, not an excel file")

    good1 = tmp_path / "good1.xlsx"
    good2 = tmp_path / "good2.xlsx"
    pd.DataFrame({"ID": [1]}).to_excel(good1, index=False)
    pd.DataFrame({"ID": [1]}).to_excel(good2, index=False)

    with pytest.raises(SetupError) as exc_info:
        check_excel_readable(str(bad), str(good1), str(good2))

    msg = str(exc_info.value)
    assert "nepodařilo otevřít" in msg
    assert str(bad) in msg


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
