"""
Agent pro měsíční přiřazení odměn SECONDARY zákazníkům.

Banka spouští tento soubor automaticky každý měsíc (např. 1. den v měsíci).
Agent sám:
  1. Načte aktuální data
  2. Detekuje dostupné měsíce
  3. Vypočítá odměny a conversion score pro každého SECONDARY zákazníka
  4. Vygeneruje Excel, CSV a JSON report
  5. Zaloguje průběh

Spuštění:
    python agent/run_agent.py

S vlastními cestami k datům:
    python agent/run_agent.py \\
        --data-6m   data/VSE_Data_6M.xlsx \\
        --data-labels data/VSE_Data_LABELY.xlsx \\
        --data-demo   data/VSE_Data_DEMO.xlsx \\
        --output-dir  agent/output

Scheduled spuštění (cron, 1. každého měsíce v 6:00):
    0 6 1 * * cd /opt/secondary_to_main && python agent/run_agent.py >> logs/agent.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Přidat kořen projektu do sys.path (funguje i při spuštění z jiné složky)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.checks import run_all_checks, SetupError
from agent.config_loader import load_config, ConfigError
from agent.data_loader import load_data, detect_history_months
from agent.reward_engine import score_customers
from agent.report_generator import generate_reports


# ── Logging ────────────────────────────────────────────────────────────────

def _setup_logging(log_file: Path | None = None) -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    return logging.getLogger("reward_agent")


# ── Hlavní logika ──────────────────────────────────────────────────────────

def run(
    path_6m: str,
    path_labels: str,
    path_demo: str,
    output_dir: str,
    run_date: str | None = None,
    history_months_n: int | None = None,
    log_file: str | None = None,
    config_path: str | None = None,
) -> dict:
    """
    Spustí celý pipeline agenta.

    Parameters
    ----------
    path_6m, path_labels, path_demo : Cesty ke zdrojovým Excel souborům
    output_dir         : Složka pro výstupní soubory
    run_date           : Datum spuštění (YYYY-MM-DD). None = dnešní datum.
    history_months_n   : Počet posledních měsíců pro výpočet průměrů.
                         None = vezme se z config.yaml (main_status.history_months).
    log_file           : Volitelná cesta k log souboru
    config_path        : Cesta k config.yaml. None = config/config.yaml.

    Returns
    -------
    Slovník s cestami k vygenerovaným souborům a základní statistikou
    """
    run_date = run_date or date.today().isoformat()
    log = _setup_logging(Path(log_file) if log_file else None)

    log.info("=" * 60)
    log.info("REWARD AGENT — spuštění")
    log.info(f"Datum:       {run_date}")
    log.info(f"Data 6M:     {path_6m}")
    log.info(f"Data labels: {path_labels}")
    log.info(f"Data demo:   {path_demo}")
    log.info(f"Výstup:      {output_dir}")
    log.info("=" * 60)

    # ── Krok 0: Kontrola prostředí ──────────────────────────────────────
    log.info("Krok 0/4 — kontroluji prostředí a data...")
    run_all_checks(path_6m, path_labels, path_demo)
    config = load_config(config_path)
    log.info(f"  Config:            {config_path or 'config/config.yaml'}")
    log.info(f"  MAIN práh příjmu:  {config['main_status']['income_threshold_czk']:,} Kč")
    log.info(f"  MAIN práh transakcí: {config['main_status']['transaction_threshold']}")
    log.info("  OK — knihovny nainstalovány, data nalezena a čitelná")

    if history_months_n is None:
        history_months_n = config["main_status"]["history_months"]

    t0 = time.time()

    # ── Krok 1: Načtení dat ────────────────────────────────────────────
    log.info("Krok 1/4 — načítám data...")
    df, months_sorted, latest_month = load_data(path_6m, path_labels, path_demo)
    log.info(f"  Detekované měsíce: {months_sorted}")
    log.info(f"  Aktuální měsíc:    {latest_month}")
    log.info(f"  Celkem zákazníků:  {len(df):,}")

    # ── Krok 2: Příprava parametrů ─────────────────────────────────────
    log.info("Krok 2/4 — připravuji parametry scoringu...")
    history = detect_history_months(months_sorted, n=history_months_n)
    current_col = f"PACTSEG_CODE_{latest_month}"
    n_secondary = (df[current_col] == "SECONDARY").sum()
    log.info(f"  Historie měsíců:   {history}")
    log.info(f"  SECONDARY zákazníků k ohodnocení: {n_secondary:,}")

    if n_secondary == 0:
        log.warning("Žádní SECONDARY zákazníci nenalezeni. Agent končí bez výstupu.")
        return {"status": "no_secondary", "run_date": run_date}

    # ── Krok 3: Scoring ────────────────────────────────────────────────
    log.info("Krok 3/4 — počítám odměny a conversion score...")
    results = score_customers(
        df_merged=df,
        current_month_col=current_col,
        history_months=history,
        run_date=run_date,
        config=config,
    )

    # Statistiky do logu
    tier_counts   = results["priority_tier"].value_counts().to_dict()
    reward_counts = {c: int(((results["vyzva_1"]==c)|(results["vyzva_2"]==c)|(results["vyzva_3"]==c)).sum()) for c in ["C1","C2","C3","C4","C5"]}
    was_main_n    = results["was_main_before"].sum()

    log.info(f"  Výsledky — priority: {tier_counts}")
    log.info(f"  Výsledky — výzvy:   {reward_counts}")
    log.info(f"  Dříve MAIN:          {was_main_n}")
    log.info(f"  Avg conversion score: {results['conversion_score'].mean():.1f}")

    # ── Krok 4: Generování reportů ─────────────────────────────────────
    log.info("Krok 4/4 — generuji výstupní soubory...")
    paths = generate_reports(results, output_dir, run_date)

    elapsed = round(time.time() - t0, 1)
    log.info("=" * 60)
    log.info(f"Agent dokončen za {elapsed}s")
    for typ, p in paths.items():
        log.info(f"  {typ:6}: {p}")
    log.info("=" * 60)

    return {
        "status":            "success",
        "run_date":          run_date,
        "elapsed_seconds":   elapsed,
        "n_secondary":       int(n_secondary),
        "priority_counts":   tier_counts,
        "reward_counts":     reward_counts,
        "was_main_before":   int(was_main_n),
        "output_files":      {k: str(v) for k, v in paths.items()},
    }


# ── CLI ────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reward agent — měsíční přiřazení odměn SECONDARY zákazníkům",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--data-6m",     default="data/VSE_Data_6M.xlsx",     help="Cesta k 6M datům")
    p.add_argument("--data-labels", default="data/VSE_Data_LABELY.xlsx", help="Cesta k labelům")
    p.add_argument("--data-demo",   default="data/VSE_Data_DEMO.xlsx",   help="Cesta k demo datům")
    p.add_argument("--output-dir",  default="agent/output",              help="Složka pro výstupy")
    p.add_argument("--run-date",    default=None, help="Datum spuštění YYYY-MM-DD (default: dnes)")
    p.add_argument("--history-months", type=int, default=None,
                   help="Počet měsíců pro průměry (default: z config.yaml)")
    p.add_argument("--log-file",    default="logs/agent.log",            help="Cesta k log souboru")
    p.add_argument("--config",      default=None,
                   help="Cesta k config.yaml (default: config/config.yaml)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        result = run(
            path_6m=args.data_6m,
            path_labels=args.data_labels,
            path_demo=args.data_demo,
            output_dir=args.output_dir,
            run_date=args.run_date,
            history_months_n=args.history_months,
            log_file=args.log_file,
            config_path=args.config,
        )
    except (SetupError, ConfigError) as e:
        print("\n" + str(e) + "\n")
        sys.exit(1)
    except FileNotFoundError as e:
        print(
            "\nCHYBA: Soubor nebo cesta nenalezena.\n"
            f"\n  {e}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zkontroluj že soubory existují ve složce 'data/'\n"
            "  - Zkontroluj že výstupní složka 'agent/output/' může být vytvořena\n"
        )
        sys.exit(1)
    except PermissionError as e:
        print(
            "\nCHYBA: Přístup odepřen.\n"
            f"\n  {e}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zavři Excel soubor pokud je otevřený\n"
            "  - Zkontroluj že máš oprávnění zapisovat do složky agent/output/\n"
        )
        sys.exit(1)

    if result.get("status") != "success":
        sys.exit(1)
