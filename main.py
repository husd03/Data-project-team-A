"""
CLI entry point for the SECONDARY → MAIN reward recommendation model.

Usage
-----
Train:
    python main.py train

Score all current SECONDARY customers:
    python main.py score --output results/scored_customers.csv

Explain a single customer:
    python main.py explain --id 7494
"""

import argparse
import json
import os
import sys

DATA_6M = "data/VSE_Data_6M.xlsx"
DATA_LABELS = "data/VSE_Data_LABELY.xlsx"
DATA_DEMO = "data/VSE_Data_DEMO.xlsx"


def cmd_train(args):
    from src.train import train

    metrics = train(
        path_6m=DATA_6M,
        path_labels=DATA_LABELS,
        path_demo=DATA_DEMO,
        cv_folds=5,
        verbose=True,
    )
    print("\n── Training complete ──────────────────────────────")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def cmd_score(args):
    from src.predict import score

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    results = score(
        path_6m=DATA_6M,
        path_labels=DATA_LABELS,
        path_demo=DATA_DEMO,
        output_csv=args.output,
    )

    print(f"\nScored {len(results)} SECONDARY customers.")
    print("\nTier distribution:")
    print(results["conversion_tier"].value_counts().to_string())
    print("\nReward distribution:")
    print(results["recommended_reward"].value_counts().to_string())
    print("\nTop 10 highest-priority customers:")
    print(results.head(10).to_string(index=False))


def cmd_explain(args):
    from src.predict import explain_customer

    result = explain_customer(
        customer_id=args.id,
        path_6m=DATA_6M,
        path_labels=DATA_LABELS,
        path_demo=DATA_DEMO,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="SECONDARY→MAIN reward recommendation model"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("train", help="Train conversion + reward models")

    score_p = sub.add_parser("score", help="Score all current SECONDARY customers")
    score_p.add_argument(
        "--output", default="results/scored_customers.csv",
        help="Output CSV path (default: results/scored_customers.csv)"
    )

    explain_p = sub.add_parser("explain", help="Explain recommendation for one customer")
    explain_p.add_argument("--id", type=int, required=True, help="Customer ID")

    args = parser.parse_args()

    if args.command == "train":
        cmd_train(args)
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "explain":
        cmd_explain(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
