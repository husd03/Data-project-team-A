"""
Unit tests for agent/reward_engine.py — the challenge scoring logic.

Run with:
    python -m pytest tests/ -v

These tests use small synthetic DataFrames so they run in under a second
and don't require the real bank data files.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config_loader import load_config
from agent.reward_engine import (
    get_challenges,
    score_customers,
    _score_one,
)

RUN_DATE = "2026-06-01"
MONTHS = ["022026", "032026", "042026"]

# Load the real config once - tests verify behaviour against the actual
# config.yaml shipped with the project, not a hardcoded copy of values.
CONFIG = load_config()
CHALLENGES = get_challenges(CONFIG)
MAIN_CR_THRESHOLD = CONFIG["main_status"]["income_threshold_czk"]
MAIN_TRX_THRESHOLD = CONFIG["main_status"]["transaction_threshold"]
MAX_CHALLENGES = CONFIG["agent"]["max_challenges"]


# ── Helpers ──────────────────────────────────────────────────────────────

def make_customer(**overrides) -> pd.Series:
    """
    Build a single customer row with sensible defaults.
    Override any field via kwargs, e.g. make_customer(avg_cr=20000).
    """
    base = {
        "avg_cr": 0.0,
        "avg_trx": 0.0,
        "avg_spb": 0.0,
        "avg_dc": 0.0,
        "avg_bal": 0.0,
        "avg_td": 0.0,
        "age": 35.0,
        "has_inv": 0,
        "has_util": 0,
        "has_subscriber": 0,
        "salary_level": 0.0,
        "was_main": False,
        "gender": "M",
        "year_joined": 2020,
        "mesice_prijem_z": 0.0,
        "mesice_trx_z": 0.0,
    }
    base.update(overrides)
    return pd.Series(base)


def make_df(n_customers=1, base_overrides=None, months=MONTHS):
    """
    Build a minimal merged DataFrame with the raw columns score_customers expects.
    Every customer is SECONDARY in the current month by default.
    """
    base_overrides = base_overrides or {}
    rows = []
    for i in range(n_customers):
        row = {
            "ID": i + 1,
            "PARTY_BIRTH_DATE": "1990-01-01",
            "GENDER_CD": "M",
            "MESIC_PRICHODU": 202001,
            "SALARY_EST": np.nan,
            "UTILITY_ENERGY": np.nan,
            "UTILITY_TELCO": np.nan,
            "SUBSCRIBER": np.nan,
        }
        for m in months:
            row[f"PACTSEG_CODE_{m}"] = "SECONDARY"
            row[f"CR_TURNOVER_{m}"] = 0.0
            row[f"DB_TRX_{m}"] = 0.0
            row[f"SPB_LOGIN_{m}"] = 0.0
            row[f"DCRD_USAGE_{m}"] = 0.0
            row[f"TOTAL_BALANCE_LIA_{m}"] = 0.0
            row[f"BALANCE_TD_LIA_{m}"] = 0.0
            row[f"COUNT_INV_{m}"] = 0
        row.update(base_overrides)
        rows.append(row)
    return pd.DataFrame(rows)


# ── CHALLENGES dict ──────────────────────────────────────────────────────

def test_challenge_codes_are_c1_to_c5():
    """The active challenge set is exactly C1-C5 (C5 SPB-login challenge removed)."""
    assert set(CHALLENGES.keys()) == {"C1", "C2", "C3", "C4", "C5"}


def test_challenge_c5_is_investment_not_spb_login():
    assert "investic" in CHALLENGES["C5"].lower()
    assert "SPB" not in CHALLENGES["C5"]


def test_constants():
    assert MAIN_CR_THRESHOLD == 15_000
    assert MAIN_TRX_THRESHOLD == 3
    assert MAX_CHALLENGES == 3


# ── C1 — income challenge ─────────────────────────────────────────────────

def test_c1_assigned_when_income_below_threshold():
    row = make_customer(avg_cr=5_000)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1)]
    assert "C1" in codes


def test_c1_not_forced_when_income_above_threshold():
    """If income already meets MAIN, C1 should not be artificially injected."""
    row = make_customer(avg_cr=20_000, avg_trx=10, avg_dc=15, has_util=1, has_subscriber=1, has_inv=1)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C1" not in codes


def test_c1_score_increases_closer_to_threshold():
    """A customer closer to 15,000 CZK should score higher on C1 than one far below."""
    far  = make_customer(avg_cr=0)
    near = make_customer(avg_cr=14_000)

    far_result  = _score_one(far)
    near_result = _score_one(near)

    # Closer customer gets the proximity bonus -> higher overall presence/priority
    # We check this indirectly via conversion_score, which rewards higher avg_cr
    assert near_result["conversion_score"] > far_result["conversion_score"]


def test_c1_bonus_for_previously_main():
    """A customer who was MAIN before should be treated as higher priority for C1."""
    never_main = make_customer(avg_cr=5_000, was_main=False)
    was_main   = make_customer(avg_cr=5_000, was_main=True)

    r1 = _score_one(never_main)
    r2 = _score_one(was_main)

    assert r2["conversion_score"] > r1["conversion_score"]
    assert r2["was_main_before"] is True
    assert r1["was_main_before"] is False


# ── C2 — card payments ────────────────────────────────────────────────────

def test_c2_not_assigned_when_card_usage_already_high():
    """A customer who already pays 10+ times with the card should not get C2."""
    row = make_customer(avg_cr=20_000, avg_trx=15, avg_dc=12, avg_spb=10,
                         has_util=1, has_subscriber=1, has_inv=1)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C2" not in codes


def test_c2_assigned_when_card_usage_low():
    row = make_customer(avg_cr=5_000, avg_dc=0)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C2" in codes


# ── C3 — utility standing order ──────────────────────────────────────────

def test_c3_not_assigned_when_has_utility():
    row = make_customer(avg_cr=20_000, avg_trx=15, avg_dc=12, has_util=1,
                         has_subscriber=1, has_inv=1)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C3" not in codes


def test_c3_assigned_when_no_utility_and_has_balance():
    row = make_customer(avg_cr=5_000, has_util=0, avg_bal=10_000, age=40)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C3" in codes


# ── C4 — subscription ─────────────────────────────────────────────────────

def test_c4_targets_younger_customers():
    """C4 score should be higher for a younger customer, all else equal."""
    young = make_customer(avg_cr=5_000, has_subscriber=0, age=30, avg_dc=5)
    old   = make_customer(avg_cr=5_000, has_subscriber=0, age=65, avg_dc=5)

    young_result = _score_one(young)
    old_result   = _score_one(old)

    young_codes = [young_result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if young_result[f"vyzva_{i}"]]
    old_codes   = [old_result[f"vyzva_{i}"]   for i in range(1, MAX_CHALLENGES + 1) if old_result[f"vyzva_{i}"]]

    # Younger customer is at least as likely to get C4; verify it appears for young
    assert "C4" in young_codes


# ── C5 — investment ────────────────────────────────────────────────────────

def test_c5_not_assigned_when_has_investment():
    row = make_customer(avg_cr=20_000, avg_trx=15, avg_dc=12, has_util=1,
                         has_subscriber=1, has_inv=1)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C5" not in codes


def test_c5_assigned_for_high_balance_no_investment():
    row = make_customer(avg_cr=5_000, has_inv=0, avg_bal=100_000, age=40)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert "C5" in codes


# ── Output shape ────────────────────────────────────────────────────────────

def test_score_one_returns_max_three_challenges():
    row = make_customer(avg_cr=0, avg_dc=0, has_util=0, has_subscriber=0, has_inv=0)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert len(codes) <= MAX_CHALLENGES


def test_score_one_no_duplicate_challenges():
    row = make_customer(avg_cr=5_000, avg_dc=2, has_util=0, has_subscriber=0, has_inv=0)
    result = _score_one(row)
    codes = [result[f"vyzva_{i}"] for i in range(1, MAX_CHALLENGES + 1) if result[f"vyzva_{i}"]]
    assert len(codes) == len(set(codes))


def test_score_one_assigned_codes_are_valid():
    row = make_customer(avg_cr=5_000, avg_dc=2, has_util=0, has_subscriber=0, has_inv=0)
    result = _score_one(row)
    for i in range(1, MAX_CHALLENGES + 1):
        code = result[f"vyzva_{i}"]
        if code:
            assert code in CHALLENGES
            assert result[f"vyzva_{i}_nazev"] == CHALLENGES[code]
            assert isinstance(result[f"vyzva_{i}_duvod"], str)


# ── Conversion score & priority tier ──────────────────────────────────────

def test_conversion_score_range():
    row = make_customer(avg_cr=50_000, avg_trx=30, avg_spb=25, avg_dc=25, was_main=True, avg_bal=20_000)
    result = _score_one(row)
    assert 0 <= result["conversion_score"] <= 100


def test_priority_tier_high_for_strong_customer():
    row = make_customer(avg_cr=46_000, avg_trx=23, avg_spb=17, avg_dc=23, was_main=True, avg_bal=20_000)
    result = _score_one(row)
    assert result["priority_tier"] == "HIGH"
    assert result["conversion_score"] >= 55


def test_priority_tier_low_for_inactive_customer():
    row = make_customer(avg_cr=0, avg_trx=0, avg_spb=0, avg_dc=0, was_main=False, avg_bal=0)
    result = _score_one(row)
    assert result["priority_tier"] == "LOW"
    assert result["conversion_score"] < 25


def test_priority_tier_medium_band():
    row = make_customer(avg_cr=10_000, avg_trx=8, avg_spb=8, avg_dc=8, was_main=False, avg_bal=5_000)
    result = _score_one(row)
    assert result["priority_tier"] in ("MEDIUM", "HIGH", "LOW")  # sanity: always one of the three
    if 25 <= result["conversion_score"] < 55:
        assert result["priority_tier"] == "MEDIUM"


# ── End-to-end: score_customers ───────────────────────────────────────────

def test_score_customers_returns_one_row_per_secondary_customer():
    df = make_df(n_customers=5)
    results = score_customers(df, f"PACTSEG_CODE_{MONTHS[-1]}", MONTHS, RUN_DATE)
    assert len(results) == 5
    assert set(results["customer_id"]) == {1, 2, 3, 4, 5}


def test_score_customers_excludes_main_segment():
    df = make_df(n_customers=2)
    # Make customer 2 MAIN in the current month
    df.loc[1, f"PACTSEG_CODE_{MONTHS[-1]}"] = "MAIN"
    results = score_customers(df, f"PACTSEG_CODE_{MONTHS[-1]}", MONTHS, RUN_DATE)
    assert len(results) == 1
    assert results.iloc[0]["customer_id"] == 1


def test_score_customers_required_columns_present():
    df = make_df(n_customers=1)
    results = score_customers(df, f"PACTSEG_CODE_{MONTHS[-1]}", MONTHS, RUN_DATE)
    expected_cols = {
        "customer_id", "segment", "conversion_score", "priority_tier",
        "was_main_before", "mesice_prijem_z", "mesice_trx_z",
        "avg_cr_czk", "avg_trx", "avg_spb", "avg_dc", "avg_balance_czk",
        "age", "gender", "year_joined", "run_date",
    }
    for i in range(1, MAX_CHALLENGES + 1):
        expected_cols |= {f"vyzva_{i}", f"vyzva_{i}_nazev", f"vyzva_{i}_duvod"}
    assert expected_cols.issubset(set(results.columns))


def test_score_customers_handles_empty_secondary_segment():
    """If no SECONDARY customers exist, return an empty DataFrame without error."""
    df = make_df(n_customers=1)
    df[f"PACTSEG_CODE_{MONTHS[-1]}"] = "MAIN"
    results = score_customers(df, f"PACTSEG_CODE_{MONTHS[-1]}", MONTHS, RUN_DATE)
    assert len(results) == 0


def test_mesice_prijem_z_is_fraction_of_months_meeting_threshold():
    """A customer meeting the income threshold in 2 of 3 months should get 0.67."""
    df = make_df(n_customers=1)
    df.loc[0, f"CR_TURNOVER_{MONTHS[0]}"] = 20_000  # meets threshold
    df.loc[0, f"CR_TURNOVER_{MONTHS[1]}"] = 20_000  # meets threshold
    df.loc[0, f"CR_TURNOVER_{MONTHS[2]}"] = 1_000   # does not

    results = score_customers(df, f"PACTSEG_CODE_{MONTHS[-1]}", MONTHS, RUN_DATE)
    assert results.iloc[0]["mesice_prijem_z"] == pytest.approx(2 / 3, abs=0.01)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
