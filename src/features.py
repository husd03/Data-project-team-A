"""
Feature engineering for SECONDARY → MAIN conversion model.

MAIN definition: incoming credit >= 15 000 CZK AND >= 3 transactions in a month.
"""

import pandas as pd
import numpy as np

MONTHS = ["112025", "122025", "012026", "022026", "032026", "042026"]

REWARD_CASH = "CASH_500"          # 500 CZK cash bonus
REWARD_SAVINGS = "SAVINGS_RATE"   # Better savings interest rate
REWARD_INVEST = "INVEST_1000"     # 1 000 CZK credited to investments


def load_and_merge(path_6m: str, path_labels: str, path_demo: str) -> pd.DataFrame:
    """Load all three source files and merge into one flat DataFrame."""
    df6m = pd.read_excel(path_6m)
    labels = pd.read_excel(path_labels)
    demo = pd.read_excel(path_demo)

    lab_wide = (
        labels
        .pivot_table(index="ID", columns="LABEL_CODE", values="LABEL_LEVEL", aggfunc="first")
        .reset_index()
    )
    lab_wide.columns.name = None

    merged = df6m.merge(lab_wide, on="ID", how="left")
    merged = merged.merge(demo, on="ID", how="left")
    return merged


def _is_main_month(df: pd.DataFrame, month: str) -> pd.Series:
    """
    True if the customer meets MAIN criteria in a given month:
      - CR_TURNOVER >= 15 000 CZK  (incoming credit)
      - DB_TRX >= 3                 (at least 3 debit transactions)
    
    Note: PACTSEG_CODE is used for the official segment label; this rule-based
    flag is used to validate and build training labels.
    """
    cr = df[f"CR_TURNOVER_{month}"].fillna(0)
    trx = df[f"DB_TRX_{month}"].fillna(0)
    return (cr >= 15_000) & (trx >= 3)


def compute_customer_features(df: pd.DataFrame, base_months: list[str]) -> pd.DataFrame:
    """
    Compute aggregated features over `base_months` for each customer.
    Returns a DataFrame indexed by ID.
    """
    feat = pd.DataFrame({"ID": df["ID"]})

    cr_cols = [f"CR_TURNOVER_{m}" for m in base_months]
    db_cols = [f"DB_TRX_{m}" for m in base_months]
    spb_cols = [f"SPB_LOGIN_{m}" for m in base_months]
    dc_cols = [f"DCRD_USAGE_{m}" for m in base_months]
    cc_cols = [f"CCRD_USAGE_{m}" for m in base_months]
    bal_lia_cols = [f"TOTAL_BALANCE_LIA_{m}" for m in base_months]
    sa_cols = [f"BALANCE_SA_ASSET_{m}" for m in base_months]
    inv_cols = [f"BALANCE_INV_OTHER_{m}" for m in base_months]
    td_cols = [f"BALANCE_TD_LIA_{m}" for m in base_months]
    count_cols = [f"TOTAL_COUNT_{m}" for m in base_months]
    cc_cnt_cols = [f"COUNT_CC_{m}" for m in base_months]
    loan_cnt_cols = [f"COUNT_LOAN_{m}" for m in base_months]
    mort_cnt_cols = [f"COUNT_MORT_{m}" for m in base_months]
    ins_cnt_cols = [f"COUNT_INS_{m}" for m in base_months]
    inv_cnt_cols = [f"COUNT_INV_{m}" for m in base_months]

    # --- Transaction / activity features ---
    feat["avg_cr_turnover"] = df[cr_cols].mean(axis=1)
    feat["max_cr_turnover"] = df[cr_cols].max(axis=1)
    feat["avg_db_trx"] = df[db_cols].mean(axis=1)
    feat["avg_spb_login"] = df[spb_cols].mean(axis=1)
    feat["avg_dcrd_usage"] = df[dc_cols].mean(axis=1)
    feat["avg_ccrd_usage"] = df[cc_cols].mean(axis=1)

    # Trend: is CR_TURNOVER growing over the period?
    if len(base_months) >= 2:
        feat["cr_trend"] = (
            df[f"CR_TURNOVER_{base_months[-1]}"].fillna(0)
            - df[f"CR_TURNOVER_{base_months[0]}"].fillna(0)
        )
    else:
        feat["cr_trend"] = 0.0

    # How many months did the customer meet the MAIN threshold?
    feat["months_near_main"] = sum(
        _is_main_month(df, m).astype(int) for m in base_months
    )

    # --- Balance features ---
    feat["avg_balance_lia"] = df[bal_lia_cols].mean(axis=1)
    feat["max_balance_lia"] = df[bal_lia_cols].max(axis=1)
    feat["avg_sa_balance"] = df[sa_cols].mean(axis=1)
    feat["avg_inv_balance"] = df[inv_cols].mean(axis=1)
    feat["avg_td_balance"] = df[td_cols].mean(axis=1)

    # --- Product holdings ---
    feat["avg_total_products"] = df[count_cols].mean(axis=1)
    feat["has_cc"] = (df[cc_cnt_cols].max(axis=1) > 0).astype(int)
    feat["has_loan"] = (df[loan_cnt_cols].max(axis=1) > 0).astype(int)
    feat["has_mortgage"] = (df[mort_cnt_cols].max(axis=1) > 0).astype(int)
    feat["has_insurance"] = (df[ins_cnt_cols].max(axis=1) > 0).astype(int)
    feat["has_investment"] = (df[inv_cnt_cols].max(axis=1) > 0).astype(int)

    # --- Label / demographic features ---
    feat["salary_est"] = df["SALARY_EST"].fillna(0)
    feat["has_salary_label"] = (df["SALARY_EST"].notna()).astype(int)
    feat["salary_high"] = (df["SALARY_EST"] >= 3).astype(int)  # AVG+25%
    feat["has_subscriber"] = (df.get("SUBSCRIBER", pd.Series(dtype=float)).notna()).astype(int)
    feat["has_utility_energy"] = (df.get("UTILITY_ENERGY", pd.Series(dtype=float)).notna()).astype(int)
    feat["has_utility_telco"] = (df.get("UTILITY_TELCO", pd.Series(dtype=float)).notna()).astype(int)

    feat["gender_m"] = (df["GENDER_CD"] == "M").astype(int)
    feat["age"] = 2026 - pd.to_datetime(df["PARTY_BIRTH_DATE"], errors="coerce").dt.year

    return feat.set_index("ID")


def assign_reward_label(feat: pd.DataFrame) -> pd.Series:
    """
    Rule-based reward assignment used to generate pseudo-labels for training.

    Priority logic (mutually exclusive, ordered):
      1. INVEST_1000  — customer shows investment appetite OR high salary OR high balance
      2. SAVINGS_RATE — customer has significant savings balance OR is a passive saver
      3. CASH_500     — everyone else (default, best for low-income / high-activity profiles)

    These rules encode domain knowledge from the bank's product team.
    The ML model learns to generalise these patterns to unseen customers.
    """
    reward = pd.Series(REWARD_CASH, index=feat.index)

    invest_mask = (
        (feat["has_investment"] == 1)
        | (feat["salary_high"] == 1)
        | (feat["avg_balance_lia"] > 200_000)
        | ((feat["age"] < 40) & (feat["avg_cr_turnover"] > 20_000))
    )

    savings_mask = (
        ~invest_mask
        & (
            (feat["avg_balance_lia"] > 50_000)
            | (feat["avg_td_balance"] > 10_000)
            | (feat["avg_sa_balance"] > 5_000)
        )
    )

    reward[savings_mask] = REWARD_SAVINGS
    reward[invest_mask] = REWARD_INVEST

    return reward


def build_training_dataset(
    path_6m: str,
    path_labels: str,
    path_demo: str,
    use_transitions: bool = True,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Build (X, y_convert, y_reward) for model training.

    y_convert : 1 if customer converted SECONDARY→MAIN in the next month
    y_reward  : recommended reward category (CASH_500 / SAVINGS_RATE / INVEST_1000)

    If use_transitions=True, each (customer, month) pair is treated as a separate
    observation, which multiplies the dataset size ~5× and improves coverage.
    """
    df = load_and_merge(path_6m, path_labels, path_demo)

    if use_transitions:
        records_X, records_conv, ids = [], [], []

        for i in range(len(MONTHS) - 1):
            m_from, m_to = MONTHS[i], MONTHS[i + 1]
            mask = df[f"PACTSEG_CODE_{m_from}"] == "SECONDARY"
            subset = df[mask].reset_index(drop=True)

            feat = compute_customer_features(subset, [m_from])
            converted = (subset[f"PACTSEG_CODE_{m_to}"] == "MAIN").astype(int).values

            records_X.append(feat)
            records_conv.append(converted)
            ids.extend(subset["ID"].tolist())

        X = pd.concat(records_X, ignore_index=True)
        y_convert = pd.Series(np.concatenate(records_conv), name="converted")
    else:
        mask = df["PACTSEG_CODE_112025"] == "SECONDARY"
        subset = df[mask].reset_index(drop=True)
        X = compute_customer_features(subset, MONTHS[:5])
        y_convert = (subset["PACTSEG_CODE_042026"] == "MAIN").astype(int).rename("converted")

    y_reward = assign_reward_label(X)

    return X, y_convert, y_reward


def build_scoring_dataset(
    path_6m: str,
    path_labels: str,
    path_demo: str,
) -> pd.DataFrame:
    """
    Build feature DataFrame for ALL current SECONDARY customers (042026).
    Used for inference / scoring.
    """
    df = load_and_merge(path_6m, path_labels, path_demo)
    mask = df["PACTSEG_CODE_042026"] == "SECONDARY"
    subset = df[mask].reset_index(drop=True)
    return compute_customer_features(subset, MONTHS[-3:])  # use last 3 months
