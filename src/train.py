"""
Model training: conversion propensity + reward recommendation.

Two models are trained:
  1. conversion_model  — XGBoost classifier predicting P(SECONDARY → MAIN)
  2. reward_model      — XGBoost multi-class classifier predicting best reward
                         (CASH_500 / SAVINGS_RATE / INVEST_1000)

Both models are saved to disk (joblib) and can be loaded for inference.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score,
    classification_report,
    average_precision_score,
)
from xgboost import XGBClassifier

from src.features import (
    build_training_dataset,
    REWARD_CASH,
    REWARD_SAVINGS,
    REWARD_INVEST,
)

MODELS_DIR = "models"
CONVERSION_MODEL_PATH = os.path.join(MODELS_DIR, "conversion_model.joblib")
REWARD_MODEL_PATH = os.path.join(MODELS_DIR, "reward_model.joblib")
REWARD_ENCODER_PATH = os.path.join(MODELS_DIR, "reward_encoder.joblib")
FEATURE_COLS_PATH = os.path.join(MODELS_DIR, "feature_cols.joblib")


def _get_xgb_params(scale_pos_weight: float = 1.0, num_class: int | None = None) -> dict:
    params = dict(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="logloss",
    )
    if num_class is not None:
        params["objective"] = "multi:softprob"
        params["num_class"] = num_class
    else:
        params["objective"] = "binary:logistic"
        params["scale_pos_weight"] = scale_pos_weight
    return params


def train(
    path_6m: str,
    path_labels: str,
    path_demo: str,
    cv_folds: int = 5,
    verbose: bool = True,
) -> dict:
    """
    Train both models, evaluate with cross-validation, save to disk.

    Returns a dict with evaluation metrics.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)

    if verbose:
        print("Building training dataset …")
    X, y_conv, y_reward = build_training_dataset(path_6m, path_labels, path_demo)

    # Drop rows with all-NaN features (edge case)
    valid = X.notna().any(axis=1)
    X = X[valid].fillna(0)
    y_conv = y_conv[valid].reset_index(drop=True)
    y_reward = y_reward[valid].reset_index(drop=True)

    feature_cols = X.columns.tolist()
    joblib.dump(feature_cols, FEATURE_COLS_PATH)

    # ── 1. Conversion model ───────────────────────────────────────────────────
    pos = y_conv.sum()
    neg = len(y_conv) - pos
    spw = neg / pos if pos > 0 else 1.0

    if verbose:
        print(f"\nConversion dataset: {len(X)} rows | positives: {pos} ({pos/len(X):.1%})")
        print(f"Scale pos weight: {spw:.1f}")

    conv_model = XGBClassifier(**_get_xgb_params(scale_pos_weight=spw))

    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
    auc_scores = cross_val_score(conv_model, X, y_conv, cv=cv, scoring="roc_auc", n_jobs=-1)
    ap_scores = cross_val_score(conv_model, X, y_conv, cv=cv, scoring="average_precision", n_jobs=-1)

    if verbose:
        print(f"Conversion model CV ROC-AUC: {auc_scores.mean():.4f} ± {auc_scores.std():.4f}")
        print(f"Conversion model CV Avg-Precision: {ap_scores.mean():.4f} ± {ap_scores.std():.4f}")

    conv_model.fit(X, y_conv)
    joblib.dump(conv_model, CONVERSION_MODEL_PATH)

    # ── 2. Reward recommendation model ───────────────────────────────────────
    le = LabelEncoder()
    y_reward_enc = le.fit_transform(y_reward)
    joblib.dump(le, REWARD_ENCODER_PATH)

    if verbose:
        print(f"\nReward distribution:\n{y_reward.value_counts().to_string()}")

    reward_model = XGBClassifier(**_get_xgb_params(num_class=len(le.classes_)))
    reward_cv_scores = cross_val_score(
        reward_model, X, y_reward_enc, cv=cv, scoring="f1_macro", n_jobs=-1
    )

    if verbose:
        print(f"Reward model CV macro-F1: {reward_cv_scores.mean():.4f} ± {reward_cv_scores.std():.4f}")

    reward_model.fit(X, y_reward_enc)
    joblib.dump(reward_model, REWARD_MODEL_PATH)

    # ── Feature importance (top 10) ──────────────────────────────────────────
    importances = pd.Series(
        conv_model.feature_importances_, index=feature_cols
    ).sort_values(ascending=False)

    if verbose:
        print("\nTop 10 features (conversion model):")
        print(importances.head(10).to_string())

    return {
        "conversion_roc_auc_mean": float(auc_scores.mean()),
        "conversion_roc_auc_std": float(auc_scores.std()),
        "conversion_avg_precision_mean": float(ap_scores.mean()),
        "reward_f1_macro_mean": float(reward_cv_scores.mean()),
        "reward_classes": le.classes_.tolist(),
        "n_train": len(X),
        "n_positive": int(pos),
        "top_features": importances.head(10).to_dict(),
    }


def load_models() -> tuple:
    """Load trained models from disk. Returns (conv_model, reward_model, encoder, feature_cols)."""
    conv_model = joblib.load(CONVERSION_MODEL_PATH)
    reward_model = joblib.load(REWARD_MODEL_PATH)
    le = joblib.load(REWARD_ENCODER_PATH)
    feature_cols = joblib.load(FEATURE_COLS_PATH)
    return conv_model, reward_model, le, feature_cols
