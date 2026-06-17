"""
Inference: score all current SECONDARY customers and produce the output table.

Output columns per customer:
  - conversion_prob   : P(becomes MAIN next month), 0-1
  - conversion_tier   : HIGH / MEDIUM / LOW based on thresholds
  - recommended_reward: CASH_500 / SAVINGS_RATE / INVEST_1000
  - reward_confidence : max softmax probability for the reward prediction
"""

import numpy as np
import pandas as pd

from src.features import build_scoring_dataset
from src.train import load_models

TIER_HIGH = "HIGH"
TIER_MEDIUM = "MEDIUM"
TIER_LOW = "LOW"

# Conversion probability thresholds (calibrated on CV results)
THRESHOLD_HIGH = 0.40
THRESHOLD_MEDIUM = 0.15


def score(
    path_6m: str,
    path_labels: str,
    path_demo: str,
    output_csv: str | None = None,
) -> pd.DataFrame:
    """
    Score all current SECONDARY customers.

    Parameters
    ----------
    path_6m, path_labels, path_demo : paths to source Excel files
    output_csv : if provided, write results to this CSV path

    Returns
    -------
    DataFrame with one row per SECONDARY customer and columns:
        ID, conversion_prob, conversion_tier, recommended_reward, reward_confidence
    """
    conv_model, reward_model, le, feature_cols = load_models()

    feat = build_scoring_dataset(path_6m, path_labels, path_demo)

    # Align columns (fill missing with 0)
    for col in feature_cols:
        if col not in feat.columns:
            feat[col] = 0.0
    X = feat[feature_cols].fillna(0)

    # Conversion probability
    conv_prob = conv_model.predict_proba(X)[:, 1]

    # Reward recommendation
    reward_proba = reward_model.predict_proba(X)
    reward_idx = reward_proba.argmax(axis=1)
    reward_label = le.inverse_transform(reward_idx)
    reward_conf = reward_proba.max(axis=1)

    # Conversion tier
    tiers = np.where(
        conv_prob >= THRESHOLD_HIGH,
        TIER_HIGH,
        np.where(conv_prob >= THRESHOLD_MEDIUM, TIER_MEDIUM, TIER_LOW),
    )

    results = pd.DataFrame(
        {
            "ID": feat.index,
            "conversion_prob": np.round(conv_prob, 4),
            "conversion_tier": tiers,
            "recommended_reward": reward_label,
            "reward_confidence": np.round(reward_conf, 4),
        }
    ).sort_values("conversion_prob", ascending=False).reset_index(drop=True)

    if output_csv:
        results.to_csv(output_csv, index=False)
        print(f"Results saved to {output_csv}")

    return results


def explain_customer(
    customer_id: int,
    path_6m: str,
    path_labels: str,
    path_demo: str,
) -> dict:
    """
    Return a human-readable explanation for a single customer's recommendation.
    """
    results = score(path_6m, path_labels, path_demo)
    row = results[results["ID"] == customer_id]

    if row.empty:
        return {"error": f"Customer {customer_id} not found in SECONDARY segment."}

    feat = build_scoring_dataset(path_6m, path_labels, path_demo)
    conv_model, reward_model, le, feature_cols = load_models()

    X = feat.loc[[customer_id], feature_cols].fillna(0)
    conv_prob = float(conv_model.predict_proba(X)[0, 1])
    reward_proba = reward_model.predict_proba(X)[0]
    reward_probs = dict(zip(le.classes_, np.round(reward_proba, 3)))

    customer_feat = feat.loc[customer_id].to_dict()

    reward = row["recommended_reward"].values[0]
    reward_reasons = {
        "INVEST_1000": [
            "Zákazník má investiční produkty nebo vysoký příjem",
            "Pravděpodobně preferuje zhodnocení peněz",
            "1 000 Kč na investice má pro něj vyšší vnímanou hodnotu než cash",
        ],
        "SAVINGS_RATE": [
            "Zákazník má vysoký zůstatek na účtu (>50 000 Kč)",
            "Lepší úrok na spoření přímo zvyšuje jeho výnos každý měsíc",
            "Motivace je trvalá – trvá po dobu spoření",
        ],
        "CASH_500": [
            "Zákazník je aktivní uživatel s nižšími zůstatky",
            "Okamžitá hotovostní odměna je nejlepší motivátor",
            "Nízká bariéra vstupu – 500 Kč je hmatatelné a rychlé",
        ],
    }

    return {
        "customer_id": customer_id,
        "conversion_probability": round(conv_prob, 4),
        "conversion_tier": row["conversion_tier"].values[0],
        "recommended_reward": reward,
        "reward_probabilities": reward_probs,
        "reward_reasoning": reward_reasons.get(reward, []),
        "key_features": {
            "avg_cr_turnover_czk": round(customer_feat.get("avg_cr_turnover", 0), 0),
            "avg_db_transactions": round(customer_feat.get("avg_db_trx", 0), 1),
            "avg_spb_logins": round(customer_feat.get("avg_spb_login", 0), 1),
            "avg_balance_czk": round(customer_feat.get("avg_balance_lia", 0), 0),
            "has_investment_product": bool(customer_feat.get("has_investment", 0)),
            "salary_bracket": int(customer_feat.get("salary_est", 0)),
        },
        "gap_to_main": {
            "needs_cr_turnover_czk": max(0, 15_000 - customer_feat.get("avg_cr_turnover", 0)),
            "needs_more_transactions": max(0, 3 - customer_feat.get("avg_db_trx", 0)),
        },
    }
