"""
tests/test_config_loader.py
============================
Unit tests for utils/config_loader.py, covering both load_config() and
the new validate_config() helper.
"""

from __future__ import annotations

import json
import os

import pytest

from utils.config_loader import load_config, validate_config


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_valid_file(self, tmp_path):
        cfg = {"obs": {"host": "localhost"}}
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps(cfg), encoding="utf-8")

        import utils.config_loader as cl
        original = cl._REPO_ROOT
        cl._REPO_ROOT = str(tmp_path)
        try:
            result = load_config("cfg.json")
        finally:
            cl._REPO_ROOT = original

        assert result == cfg

    def test_missing_file_returns_empty(self, tmp_path):
        import utils.config_loader as cl
        original = cl._REPO_ROOT
        cl._REPO_ROOT = str(tmp_path)
        try:
            result = load_config("nonexistent.json")
        finally:
            cl._REPO_ROOT = original
        assert result == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json}", encoding="utf-8")

        import utils.config_loader as cl
        original = cl._REPO_ROOT
        cl._REPO_ROOT = str(tmp_path)
        try:
            result = load_config("bad.json")
        finally:
            cl._REPO_ROOT = original
        assert result == {}


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_empty_config_gets_all_defaults(self):
        result = validate_config({})
        assert "obs" in result
        assert result["obs"]["host"] == "localhost"
        assert result["obs"]["port"] == 4455
        assert "voice" in result
        assert result["voice"]["whisper_model"] == "base"
        assert "logging" in result
        assert result["logging"]["level"] == "INFO"

    def test_user_values_override_defaults(self):
        result = validate_config({"obs": {"host": "remote", "port": 9999}})
        assert result["obs"]["host"] == "remote"
        assert result["obs"]["port"] == 9999
        # Other keys filled from defaults
        assert result["obs"]["password"] == ""

    def test_extra_top_level_keys_preserved(self):
        result = validate_config({"custom_key": "custom_value"})
        assert result["custom_key"] == "custom_value"

    def test_invalid_section_type_replaced_with_defaults(self):
        result = validate_config({"voice": "not-a-dict"})
        assert isinstance(result["voice"], dict)
        assert result["voice"]["whisper_model"] == "base"

    def test_full_config_unchanged(self):
        full = {
            "obs": {"host": "h", "port": 1, "password": "p", "path": ""},
            "twitch": {
                "client_id": "c",
                "client_secret": "s",
                "channel": "ch",
                "browser_url": "https://twitch.tv",
            },
            "games": {"valorant": "C:\\val.exe"},
            "voice": {
                "whisper_model": "small",
                "tts_rate": 180,
                "tts_volume": 0.9,
                "listen_timeout": 3,
                "phrase_time_limit": 8,
            },
            "logging": {"level": "DEBUG", "file": "my.log"},
        }
        result = validate_config(full)
        assert result["obs"]["host"] == "h"
        assert result["voice"]["whisper_model"] == "small"
        assert result["logging"]["level"] == "DEBUG"
        assert result["games"] == {"valorant": "C:\\val.exe"}
