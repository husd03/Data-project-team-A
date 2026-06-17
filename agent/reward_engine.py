"""
Challenge assignment engine — přiřazuje výzvy místo odměn.

Výzvy (C1-C5) a jejich scoring jsou definovány v config/config.yaml.
Tento modul obsahuje LOGIKU (které podmínky se vyhodnocují), config
obsahuje ČÍSLA (thresholdy, body, normalizéry, názvy).

Aby se změnily thresholdy nebo váhy, upravuj config/config.yaml —
ne tento soubor. Viz VIBECODING.md pro návod.
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

from agent.config_loader import load_config

warnings.filterwarnings("ignore")


# Loaded lazily so tests can pass a custom config without touching disk
_DEFAULT_CONFIG = None


def _get_default_config() -> dict:
    global _DEFAULT_CONFIG
    if _DEFAULT_CONFIG is None:
        _DEFAULT_CONFIG = load_config()
    return _DEFAULT_CONFIG


def get_challenges(config: dict | None = None) -> dict:
    """Return {code: display_name} for all configured challenges."""
    cfg = config or _get_default_config()
    return {code: c["name"] for code, c in cfg["challenges"].items()}


# ── Main scoring entry point ──────────────────────────────────────────────

def score_customers(df_merged, current_month_col, history_months, run_date, config: dict | None = None):
    cfg = config or _get_default_config()

    main_cr_threshold  = cfg["main_status"]["income_threshold_czk"]
    main_trx_threshold = cfg["main_status"]["transaction_threshold"]

    sec = df_merged[df_merged[current_month_col] == "SECONDARY"].copy()

    def avg(prefix):
        cols = [f"{prefix}_{m}" for m in history_months if f"{prefix}_{m}" in sec.columns]
        return sec[cols].mean(axis=1).fillna(0) if cols else pd.Series(0.0, index=sec.index)

    def any_pos(prefix):
        cols = [f"{prefix}_{m}" for m in history_months if f"{prefix}_{m}" in sec.columns]
        return (sec[cols].max(axis=1) > 0).astype(int) if cols else pd.Series(0, index=sec.index)

    sec["avg_cr"]  = avg("CR_TURNOVER")
    sec["avg_trx"] = avg("DB_TRX")
    sec["avg_spb"] = avg("SPB_LOGIN")
    sec["avg_dc"]  = avg("DCRD_USAGE")
    sec["avg_bal"] = avg("TOTAL_BALANCE_LIA")
    sec["avg_td"]  = avg("BALANCE_TD_LIA")
    sec["has_inv"] = any_pos("COUNT_INV")

    all_m = [c.replace("CR_TURNOVER_", "") for c in sec.columns if c.startswith("CR_TURNOVER_")]
    n_all = len(all_m)
    sec["mesice_prijem_splneno"] = sum((sec[f"CR_TURNOVER_{m}"].fillna(0) >= main_cr_threshold).astype(int) for m in all_m)
    sec["mesice_trx_splneno"]    = sum((sec[f"DB_TRX_{m}"].fillna(0) >= main_trx_threshold).astype(int) for m in all_m)
    sec["mesice_prijem_z"] = (sec["mesice_prijem_splneno"] / n_all).round(2) if n_all else 0.0
    sec["mesice_trx_z"]    = (sec["mesice_trx_splneno"] / n_all).round(2) if n_all else 0.0

    sec["age"] = (pd.to_datetime(run_date).year - pd.to_datetime(sec["PARTY_BIRTH_DATE"], errors="coerce").dt.year).fillna(0)
    sec["gender"] = sec.get("GENDER_CD", pd.Series("", index=sec.index)).fillna("")
    mesic = pd.to_numeric(sec.get("MESIC_PRICHODU", pd.Series(0, index=sec.index)), errors="coerce").fillna(0)
    sec["year_joined"]    = (mesic // 100).astype(int)
    sec["salary_level"]   = pd.to_numeric(sec.get("SALARY_EST", pd.Series(0, index=sec.index)), errors="coerce").fillna(0)
    sec["has_util"]       = ((sec.get("UTILITY_ENERGY", pd.Series(np.nan, index=sec.index)).notna().astype(int) +
                              sec.get("UTILITY_TELCO",  pd.Series(np.nan, index=sec.index)).notna().astype(int)) > 0).astype(int)
    sec["has_subscriber"] = sec.get("SUBSCRIBER", pd.Series(np.nan, index=sec.index)).notna().astype(int)
    seg_cols = [c for c in sec.columns if c.startswith("PACTSEG_CODE_")]
    sec["was_main"] = sec[seg_cols].eq("MAIN").any(axis=1)

    results = sec.apply(lambda row: _score_one(row, cfg), axis=1, result_type="expand")
    results["run_date"] = run_date
    results.index = sec.index
    results.insert(0, "customer_id", sec["ID"].values)
    return results.reset_index(drop=True)


# ── Per-customer scoring ───────────────────────────────────────────────────

def _score_one(row, config: dict | None = None):
    cfg = config or _get_default_config()

    main_cr_threshold = cfg["main_status"]["income_threshold_czk"]
    max_challenges    = cfg["agent"]["max_challenges"]
    ch_cfg            = cfg["challenges"]
    cs_cfg            = cfg["conversion_score"]

    avg_cr  = float(row.get("avg_cr", 0) or 0)
    avg_trx = float(row.get("avg_trx", 0) or 0)
    avg_spb = float(row.get("avg_spb", 0) or 0)
    avg_dc  = float(row.get("avg_dc", 0) or 0)
    avg_bal = float(row.get("avg_bal", 0) or 0)
    avg_td  = float(row.get("avg_td", 0) or 0)
    age     = float(row.get("age", 0) or 0)
    has_inv = int(row.get("has_inv", 0) or 0)
    has_util  = int(row.get("has_util", 0) or 0)
    has_sub   = int(row.get("has_subscriber", 0) or 0)
    sal_lvl   = float(row.get("salary_level", 0) or 0)
    was_main  = bool(row.get("was_main", False))
    scores = {}
    reasons = {}

    # ── C1 — income ──────────────────────────────────────────────────────
    c1 = ch_cfg["C1"]["points"]
    gap_cr = max(0.0, main_cr_threshold - avg_cr)
    s1, sc1 = [], 0
    if gap_cr > 0:
        sc1 += c1["income_below_threshold_base"]
        sc1 += min(c1["proximity_bonus_max"], int((1 - gap_cr / main_cr_threshold) * c1["proximity_bonus_max"]))
        if was_main:
            sc1 += c1["was_main_before"]
            s1.append("dříve byl MAIN")
        if avg_trx >= 3:
            sc1 += c1["transactions_already_met"]
            s1.append("transakce OK, chybí jen příjem")
        s1.append(f"příjem {avg_cr:,.0f} Kč/měs., chybí {gap_cr:,.0f} Kč")
    scores["C1"] = sc1
    reasons["C1"] = "; ".join(s1[:2]) if s1 else "splněno"

    # ── C2 — card payments ───────────────────────────────────────────────
    c2t = ch_cfg["C2"]["thresholds"]
    c2p = ch_cfg["C2"]["points"]
    s2, sc2 = [], 0
    if avg_dc < c2t["card_usage_target"]:
        sc2 += c2p["below_target_base"]
        if avg_dc >= c2t["card_usage_close_band"]:
            sc2 += c2p["close_to_target"]
            s2.append(f"{avg_dc:.0f} plateb — blízko cíle")
        elif avg_dc > 0:
            sc2 += c2p["some_usage"]
            s2.append(f"{avg_dc:.0f} plateb kartou")
        else:
            s2.append("kartu nepoužívá")
        if avg_cr >= c2t["income_for_card_bonus"]:
            sc2 += c2p["has_income_bonus"]
            s2.append("má příjem — může platit kartou")
    scores["C2"] = sc2
    reasons["C2"] = "; ".join(s2[:2]) if s2 else "splněno"

    # ── C3 — utility standing order ─────────────────────────────────────
    c3t = ch_cfg["C3"]["thresholds"]
    c3p = ch_cfg["C3"]["points"]
    s3, sc3 = [], 0
    if not has_util:
        sc3 += c3p["no_utility_base"]
        if avg_bal > c3t["balance_for_household_bonus"]:
            sc3 += c3p["has_balance_bonus"]
            s3.append("má prostředky pro domácí výdaje")
        if age >= c3t["min_age_for_household_bonus"]:
            sc3 += c3p["age_bonus"]
            s3.append("pravděpodobně platí domácnost")
        s3.append("energie/telco zatím není přes banku")
    scores["C3"] = sc3
    reasons["C3"] = "; ".join(s3[:2]) if s3 else "splněno"

    # ── C4 — subscription ────────────────────────────────────────────────
    c4t = ch_cfg["C4"]["thresholds"]
    c4p = ch_cfg["C4"]["points"]
    s4, sc4 = [], 0
    if not has_sub:
        sc4 += c4p["no_subscription_base"]
        if age < c4t["max_age_for_streaming_bonus"]:
            sc4 += c4p["young_age_bonus"]
            s4.append(f"věk {int(age)} — typický uživatel streamingu")
        if avg_dc >= c4t["min_card_usage_for_active_bonus"]:
            sc4 += c4p["active_card_bonus"]
            s4.append("aktivní kartou — přechod snadný")
        s4.append("předplatné zatím není přes banku")
    scores["C4"] = sc4
    reasons["C4"] = "; ".join(s4[:2]) if s4 else "splněno"

    # ── C5 — investment ──────────────────────────────────────────────────
    c5t = ch_cfg["C5"]["thresholds"]
    c5p = ch_cfg["C5"]["points"]
    s5, sc5 = [], 0
    if not has_inv:
        sc5 += c5p["no_investment_base"]
        if sal_lvl >= c5t["min_salary_level"]:
            sc5 += c5p["high_salary_bonus"]
            s5.append("vysoký příjem")
        if avg_bal > c5t["balance_for_investment_bonus"]:
            sc5 += c5p["high_balance_bonus"]
            s5.append(f"zůstatek {avg_bal:,.0f} Kč")
        if avg_td > c5t["term_deposit_threshold"]:
            sc5 += c5p["term_deposit_bonus"]
            s5.append("má terminovaný vklad")
        if age < c5t["max_age_for_horizon_bonus"]:
            sc5 += c5p["young_age_bonus"]
            s5.append(f"věk {int(age)} let")
        s5.append("nemá investiční produkt")
    scores["C5"] = sc5
    reasons["C5"] = "; ".join(s5[:2]) if s5 else "splněno"

    # ── Select top challenges ────────────────────────────────────────────
    ranked = sorted([(c, s) for c, s in scores.items() if s > 0], key=lambda x: x[1], reverse=True)
    top = [c for c, _ in ranked[:max_challenges]]
    if scores["C1"] > 0 and "C1" not in top:
        if top:
            top[-1] = "C1"
        else:
            top = ["C1"]

    # ── Conversion score ──────────────────────────────────────────────────
    w = cs_cfg["weights"]
    conv  = min(avg_cr / main_cr_threshold, 1.0) * w["income_ratio"]
    conv += min(avg_trx / cs_cfg["transaction_normalizer"], 1.0) * w["transaction_activity"]
    conv += min(avg_spb / cs_cfg["spb_normalizer"], 1.0) * w["spb_engagement"]
    conv += min(avg_dc / cs_cfg["card_normalizer"], 1.0) * w["card_usage"]
    if was_main:
        conv += w["was_main_bonus"]
    if avg_bal > cs_cfg["balance_bonus_threshold_czk"]:
        conv += w["balance_bonus"]
    conv_score = round(min(conv, 100), 1)

    tiers = cs_cfg["priority_tiers"]
    if conv_score >= tiers["high_min"]:
        tier = "HIGH"
    elif conv_score >= tiers["medium_min"]:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    res = {
        "segment": "SECONDARY", "conversion_score": conv_score, "priority_tier": tier,
        "was_main_before": bool(row.get("was_main", False)),
        "mesice_prijem_z": float(row.get("mesice_prijem_z", 0.0)),
        "mesice_trx_z": float(row.get("mesice_trx_z", 0.0)),
        "avg_cr_czk": round(avg_cr, 0), "avg_trx": round(avg_trx, 1),
        "avg_spb": round(avg_spb, 1), "avg_dc": round(avg_dc, 1),
        "avg_balance_czk": round(avg_bal, 0), "age": int(age),
        "gender": str(row.get("gender", "")), "year_joined": int(row.get("year_joined", 0) or 0),
    }

    challenge_names = get_challenges(cfg)
    for i in range(1, max_challenges + 1):
        code = top[i - 1] if i <= len(top) else ""
        res[f"vyzva_{i}"]       = code
        res[f"vyzva_{i}_nazev"] = challenge_names.get(code, "") if code else ""
        res[f"vyzva_{i}_duvod"] = reasons.get(code, "")          if code else ""
    return res
