"""
Pre-flight checks for the reward agent.

Before doing any real work, the agent checks for the two most common
setup mistakes and prints a clear, actionable message in Czech instead
of a raw Python traceback:

  1. Required Python packages are not installed
     -> "Run instalation.bat"

  2. Source Excel data files are missing
     -> "Copy your data files into the data/ folder"

Both checks raise SetupError, which run_agent.py catches and prints
without a traceback.
"""

from __future__ import annotations

from pathlib import Path


class SetupError(Exception):
    """Raised when the environment is not ready to run the agent."""


# ── Required packages ───────────────────────────────────────────────────

# (import name, pip package name)
REQUIRED_PACKAGES = [
    ("pandas",   "pandas"),
    ("numpy",    "numpy"),
    ("openpyxl", "openpyxl"),
]


def check_dependencies() -> None:
    """
    Verify that all required Python packages can be imported.
    Raises SetupError with installation instructions if any are missing.
    """
    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        pkgs = ", ".join(missing)
        raise SetupError(
            "CHYBA: Chybí potřebné Python knihovny.\n"
            "\n"
            f"  Chybí: {pkgs}\n"
            "\n"
            "  ŘEŠENÍ:\n"
            "  1. Spusť dvojklikem soubor 'instalation.bat'\n"
            "     (je ve stejné složce jako tento agent)\n"
            "\n"
            "  Nebo z příkazové řádky:\n"
            "     python -m pip install -r requirements.txt\n"
        )


# ── Required data files ─────────────────────────────────────────────────

def check_data_files(path_6m: str, path_labels: str, path_demo: str) -> None:
    """
    Verify that all three source Excel files exist and are non-empty.
    Raises SetupError with copy instructions if any are missing.
    """
    files = {
        "6M data (transakce, zůstatky, produkty)": path_6m,
        "Labely (mzda, utility, subscriber)":       path_labels,
        "Demografie (věk, pohlaví, město)":          path_demo,
    }

    missing = []
    empty = []
    for label, path in files.items():
        p = Path(path)
        if not p.exists():
            missing.append((label, path))
        elif p.stat().st_size == 0:
            empty.append((label, path))

    if missing or empty:
        lines = [
            "CHYBA: Chybí zdrojová data.\n",
        ]

        if missing:
            lines.append("  Tyto soubory nebyly nalezeny:")
            for label, path in missing:
                lines.append(f"    - {path}   ({label})")
            lines.append("")

        if empty:
            lines.append("  Tyto soubory existují, ale jsou prázdné (0 B):")
            for label, path in empty:
                lines.append(f"    - {path}   ({label})")
            lines.append("")

        lines += [
            "  ŘEŠENÍ:",
            "  1. Vlož data od banky do složky 'data/'",
            "",
            "  2. Spusť agenta znovu (spustit_agenta.bat)",
            "",
            "  Pokud máš soubory na jiném místě nebo s jinými názvy, zadej cesty parametrem:",
            "     python agent/run_agent.py --data-6m C:\\cesta\\nazev.xlsx ...",
        ]
        raise SetupError("\n".join(lines))


# ── Excel file readability ─────────────────────────────────────────────

def check_excel_readable(path_6m: str, path_labels: str, path_demo: str) -> None:
    """
    Try to actually open each Excel file. Catches corrupted files,
    wrong format (e.g. a renamed .csv), or files open in Excel
    (locked for reading on Windows).
    """
    import pandas as pd

    files = {
        "6M data":   path_6m,
        "Labely":    path_labels,
        "Demografie": path_demo,
    }

    problems = []
    for label, path in files.items():
        try:
            pd.read_excel(path, nrows=1)
        except Exception as e:  # noqa: BLE001 - we want to catch everything here
            problems.append((label, path, str(e)))

    if problems:
        lines = ["CHYBA: Soubor s daty se nepodařilo otevřít.\n"]
        for label, path, err in problems:
            lines.append(f"  {label}: {path}")
            lines.append(f"    -> {err}")
            lines.append("")

        lines += [
            "  MOŽNÉ PŘÍČINY:",
            "  - Soubor je otevřený v Excelu (zavři ho a zkus znovu)",
            "  - Soubor není platný .xlsx (zkontroluj že nejde o .csv s jinou přípponou)",
            "  - Soubor je poškozený - nahraj ho znovu z bankovního systému",
        ]
        raise SetupError("\n".join(lines))


def run_all_checks(path_6m: str, path_labels: str, path_demo: str) -> None:
    """Run all pre-flight checks in order. Raises SetupError on first failure."""
    check_dependencies()
    check_data_files(path_6m, path_labels, path_demo)
    check_excel_readable(path_6m, path_labels, path_demo)
