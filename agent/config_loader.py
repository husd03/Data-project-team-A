"""
Configuration loader for the challenge assignment agent.

Loads config/config.yaml (or a path passed via --config) and provides
typed access to thresholds, scoring weights, and challenge names used
by agent/reward_engine.py.

Keeping configuration in YAML means thresholds and scoring weights can
be tuned without touching Python code — see VIBECODING.md for guided
prompts on how to do this safely with an AI assistant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


class ConfigError(Exception):
    """Raised when config.yaml is missing, malformed, or missing required keys."""


# ── Loading ──────────────────────────────────────────────────────────────

def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    Load and validate the agent configuration.

    Parameters
    ----------
    path : Path to config.yaml. Defaults to config/config.yaml in the
           project root.

    Returns
    -------
    Parsed configuration as a nested dict.

    Raises
    ------
    ConfigError if the file is missing, not valid YAML, or missing any
    of the required top-level sections / keys.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise ConfigError(
            "CHYBA: Konfigurační soubor nenalezen.\n"
            f"\n  Hledáno: {config_path}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zkontroluj že složka 'config/' obsahuje soubor 'config.yaml'\n"
            "  - Pokud jsi config přesunul, zadej cestu parametrem --config\n"
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(
            "CHYBA: Konfigurační soubor 'config.yaml' nelze přečíst — neplatný YAML formát.\n"
            f"\n  Soubor: {config_path}\n"
            f"  Chyba:  {e}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zkontroluj odsazení (YAML používá mezery, ne tabulátory)\n"
            "  - Zkontroluj že každý klíč má ':' a hodnoty jsou na správném místě\n"
            "  - Pokud jsi soubor upravoval ručně, zkus vrátit poslední fungující verzi z Gitu:\n"
            "      git checkout config/config.yaml\n"
        )

    if cfg is None:
        raise ConfigError(f"CHYBA: Konfigurační soubor '{config_path}' je prázdný.")

    _validate(cfg, config_path)
    return cfg


# ── Validation ───────────────────────────────────────────────────────────

REQUIRED_SECTIONS = ["main_status", "agent", "conversion_score", "challenges"]
REQUIRED_CHALLENGES = ["C1", "C2", "C3", "C4", "C5"]


def _validate(cfg: dict, config_path: Path) -> None:
    missing_sections = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing_sections:
        raise ConfigError(
            "CHYBA: Konfigurační soubor postrádá povinné sekce.\n"
            f"\n  Soubor: {config_path}\n"
            f"  Chybí sekce: {', '.join(missing_sections)}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zkontroluj že config.yaml obsahuje sekce: "
            f"{', '.join(REQUIRED_SECTIONS)}\n"
            "  - Pokud jsi sekci omylem smazal, vrať poslední fungující verzi:\n"
            "      git checkout config/config.yaml\n"
        )

    missing_challenges = [c for c in REQUIRED_CHALLENGES if c not in cfg.get("challenges", {})]
    if missing_challenges:
        raise ConfigError(
            "CHYBA: Konfigurační soubor postrádá definice výzev.\n"
            f"\n  Soubor: {config_path}\n"
            f"  Chybí výzvy: {', '.join(missing_challenges)}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Zkontroluj že sekce 'challenges' obsahuje C1 až C5\n"
            "  - Pokud jsi výzvu úmyslně odstranil, ujisti se že jsi také\n"
            "    upravil agent/reward_engine.py odpovídajícím způsobem\n"
            "    (viz VIBECODING.md)\n"
        )

    # Spot-check a couple of deeply-nested required keys with clear errors
    try:
        cfg["main_status"]["income_threshold_czk"]
        cfg["main_status"]["transaction_threshold"]
        cfg["main_status"]["history_months"]
        cfg["agent"]["max_challenges"]
        cfg["conversion_score"]["weights"]
        cfg["conversion_score"]["priority_tiers"]["high_min"]
        cfg["conversion_score"]["priority_tiers"]["medium_min"]
        for code in REQUIRED_CHALLENGES:
            cfg["challenges"][code]["name"]
    except (KeyError, TypeError) as e:
        raise ConfigError(
            "CHYBA: Konfigurační soubor postrádá povinnou hodnotu.\n"
            f"\n  Soubor: {config_path}\n"
            f"  Chybějící klíč: {e}\n"
            "\n  ŘEŠENÍ:\n"
            "  - Porovnej svůj config.yaml se šablonou v Gitu:\n"
            "      git diff config/config.yaml\n"
            "  - Nebo vrať poslední fungující verzi:\n"
            "      git checkout config/config.yaml\n"
        )
