"""
Unit tests for agent/config_loader.py — loading and validating config.yaml.

Run with:
    python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config_loader import load_config, ConfigError, DEFAULT_CONFIG_PATH


# ── Loading the real shipped config ────────────────────────────────────────

def test_default_config_loads_without_error():
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_default_config_path_exists():
    assert DEFAULT_CONFIG_PATH.exists()


def test_default_config_has_required_sections():
    cfg = load_config()
    for section in ("main_status", "agent", "conversion_score", "challenges"):
        assert section in cfg


def test_default_config_has_all_five_challenges():
    cfg = load_config()
    assert set(cfg["challenges"].keys()) == {"C1", "C2", "C3", "C4", "C5"}


def test_default_config_income_threshold_is_15000():
    cfg = load_config()
    assert cfg["main_status"]["income_threshold_czk"] == 15000


# ── Missing file ─────────────────────────────────────────────────────────

def test_missing_file_raises_config_error(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ConfigError) as exc_info:
        load_config(missing)
    msg = str(exc_info.value)
    assert "nenalezen" in msg
    assert str(missing) in msg


# ── Invalid YAML ─────────────────────────────────────────────────────────

def test_invalid_yaml_raises_config_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("main_status:\n  income_threshold_czk: 15000\n  bad_indent\nfoo")

    with pytest.raises(ConfigError) as exc_info:
        load_config(bad)
    msg = str(exc_info.value)
    assert "YAML" in msg or "config.yaml" in msg


def test_empty_file_raises_config_error(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")

    with pytest.raises(ConfigError) as exc_info:
        load_config(empty)
    assert "prázdný" in str(exc_info.value)


# ── Missing required sections / keys ────────────────────────────────────

def _write_minimal_valid_config(path: Path) -> dict:
    """Returns a minimal but fully valid config as a dict, written to path."""
    cfg = {
        "main_status": {
            "income_threshold_czk": 15000,
            "transaction_threshold": 3,
            "history_months": 3,
        },
        "agent": {"max_challenges": 3},
        "conversion_score": {
            "weights": {
                "income_ratio": 35, "transaction_activity": 20,
                "spb_engagement": 15, "card_usage": 10,
                "was_main_bonus": 15, "balance_bonus": 5,
            },
            "transaction_normalizer": 20,
            "spb_normalizer": 20,
            "card_normalizer": 20,
            "balance_bonus_threshold_czk": 10000,
            "priority_tiers": {"high_min": 55, "medium_min": 25},
        },
        "challenges": {
            f"C{i}": {"name": f"Challenge {i}", "points": {}, "thresholds": {}}
            for i in range(1, 6)
        },
    }
    path.write_text(yaml.dump(cfg))
    return cfg


def test_minimal_valid_config_passes(tmp_path):
    p = tmp_path / "config.yaml"
    _write_minimal_valid_config(p)
    cfg = load_config(p)
    assert cfg["agent"]["max_challenges"] == 3


def test_missing_top_level_section_raises(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = _write_minimal_valid_config(p)
    del cfg["conversion_score"]
    p.write_text(yaml.dump(cfg))

    with pytest.raises(ConfigError) as exc_info:
        load_config(p)
    msg = str(exc_info.value)
    assert "conversion_score" in msg
    assert "git checkout" in msg


def test_missing_challenge_raises(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = _write_minimal_valid_config(p)
    del cfg["challenges"]["C5"]
    p.write_text(yaml.dump(cfg))

    with pytest.raises(ConfigError) as exc_info:
        load_config(p)
    msg = str(exc_info.value)
    assert "C5" in msg


def test_missing_nested_key_raises(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = _write_minimal_valid_config(p)
    del cfg["conversion_score"]["priority_tiers"]["medium_min"]
    p.write_text(yaml.dump(cfg))

    with pytest.raises(ConfigError) as exc_info:
        load_config(p)
    msg = str(exc_info.value)
    assert "Chybějící klíč" in msg


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
