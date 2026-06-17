"""
Data loader pro agenta.

Načte tři zdrojové soubory, spojí je a automaticky detekuje
dostupné měsíce z názvů sloupců — agent funguje bez ohledu
na to, kolik měsíců dat banka dodá.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")


def load_data(
    path_6m: str | Path,
    path_labels: str | Path,
    path_demo: str | Path,
) -> tuple[pd.DataFrame, list[str], str]:
    """
    Načte a spojí všechna data.

    Returns
    -------
    df_merged     : Spojený DataFrame, jeden řádek = jeden zákazník
    months_sorted : Seřazené měsíční kódy (MMYYYY) detekované z dat
    latest_month  : Kód posledního dostupného měsíce
    """
    df6m   = pd.read_excel(path_6m).drop_duplicates("ID")
    labels = pd.read_excel(path_labels)
    demo   = pd.read_excel(path_demo).drop_duplicates("ID")

    # ── Pivot labels → wide format ─────────────────────────────────────
    label_dfs = []
    for code in labels["LABEL_CODE"].unique():
        sub = (labels[labels["LABEL_CODE"] == code]
               .drop_duplicates("ID")[["ID", "LABEL_SUBCODE", "LABEL_LEVEL"]])
        sub = sub.rename(columns={
            "LABEL_SUBCODE": f"{code}_BAND",
            "LABEL_LEVEL":   code,
        })
        label_dfs.append(sub.set_index("ID"))

    labels_wide = pd.concat(label_dfs, axis=1).reset_index() if label_dfs else pd.DataFrame({"ID": df6m["ID"]})

    # ── Merge ──────────────────────────────────────────────────────────
    df = (df6m
          .merge(demo,        on="ID", how="left")
          .merge(labels_wide, on="ID", how="left"))

    # ── Detekce dostupných měsíců z názvů sloupců ─────────────────────
    month_pattern = re.compile(r"PACTSEG_CODE_(\d{6})$")
    raw_months = []
    for col in df.columns:
        m = month_pattern.match(col)
        if m:
            raw_months.append(m.group(1))

    months_sorted = _sort_months(raw_months)
    if not months_sorted:
        raise ValueError("V datech nenalezeny žádné PACTSEG_CODE_MMYYYY sloupce.")

    latest_month = months_sorted[-1]
    return df, months_sorted, latest_month


def _sort_months(months: list[str]) -> list[str]:
    """
    Seřadí měsíční kódy ve formátu MMYYYY chronologicky.
    Např. ['042026', '112025', '012026'] → ['112025', '012026', '042026']
    """
    def key(m: str) -> tuple[int, int]:
        mm, yyyy = int(m[:2]), int(m[2:])
        return yyyy, mm

    return sorted(set(months), key=key)


def detect_history_months(months_sorted: list[str], n: int = 3) -> list[str]:
    """Vrátí posledních n měsíců pro výpočet průměrů."""
    return months_sorted[-n:] if len(months_sorted) >= n else months_sorted
