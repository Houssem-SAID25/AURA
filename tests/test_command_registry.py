"""
tests/test_command_registry.py
==============================
Unit tests for core/command_registry.py.
"""

import json
import os
import pytest
from core.command_registry import CommandRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry_file(tmp_path) -> str:
    """Write a minimal commands.json and return its path."""
    data = {
        "stream_cs2": {
            "description": "CS2 full stream setup",
            "keywords": ["stream cs2", "go live cs2"],
            "intent": "stream",
            "game": "counter-strike 2",
            "actions": ["launch_obs", "launch_game", "open_twitch"],
        },
        "stream_valorant": {
            "description": "Valorant stream setup",
            "keywords": ["stream valorant"],
            "intent": "stream",
            "game": "valorant",
            "actions": ["launch_obs", "launch_game", "open_twitch"],
        },
    }
    path = tmp_path / "commands.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture()
def registry(registry_file) -> CommandRegistry:
    return CommandRegistry(registry_path=registry_file)


@pytest.fixture()
def empty_registry(tmp_path) -> CommandRegistry:
    """Registry pointing at a non-existent file."""
    return CommandRegistry(registry_path=str(tmp_path / "missing.json"))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestRegistryLoading:
    def test_loads_commands(self, registry):
        assert "stream_cs2" in registry.list_commands()
        assert "stream_valorant" in registry.list_commands()

    def test_missing_file_gives_empty_registry(self, empty_registry):
        assert empty_registry.list_commands() == []

    def test_invalid_json_gives_empty_registry(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{")
        reg = CommandRegistry(registry_path=str(bad_file))
        assert reg.list_commands() == []

    def test_reload(self, registry_file, registry):
        """Adding a new command to the file and reloading should pick it up."""
        with open(registry_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["stream_fortnite"] = {
            "keywords": ["stream fortnite"],
            "intent": "stream",
            "game": "fortnite",
            "actions": ["launch_obs", "launch_game"],
        }
        with open(registry_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        registry.reload()
        assert "stream_fortnite" in registry.list_commands()


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class TestRegistryMatch:
    def test_exact_keyword_match(self, registry):
        cmd = registry.match("stream cs2")
        assert cmd is not None
        assert cmd["name"] == "stream_cs2"
        assert cmd["game"] == "counter-strike 2"

    def test_keyword_within_longer_sentence(self, registry):
        cmd = registry.match("i want to stream cs2 tonight")
        assert cmd is not None
        assert cmd["name"] == "stream_cs2"

    def test_longer_keyword_wins(self, registry):
        """'go live cs2' is longer than 'stream cs2' — both in same command."""
        cmd = registry.match("go live cs2 right now")
        assert cmd is not None
        assert cmd["name"] == "stream_cs2"

    def test_no_match_returns_none(self, registry):
        cmd = registry.match("what is the weather today")
        assert cmd is None

    def test_empty_input_returns_none(self, registry):
        assert registry.match("") is None

    def test_none_input_returns_none(self, registry):
        assert registry.match(None) is None  # type: ignore[arg-type]

    def test_empty_registry_returns_none(self, empty_registry):
        assert empty_registry.match("stream cs2") is None

    def test_returned_dict_has_expected_keys(self, registry):
        cmd = registry.match("stream valorant")
        assert cmd is not None
        for key in ("name", "type", "actions", "game", "scene", "raw", "source"):
            assert key in cmd

    def test_actions_list_returned(self, registry):
        cmd = registry.match("stream cs2")
        assert cmd is not None
        assert isinstance(cmd["actions"], list)
        assert "launch_obs" in cmd["actions"]

    def test_source_is_registry(self, registry):
        cmd = registry.match("stream cs2")
        assert cmd is not None
        assert cmd["source"] == "registry"

    def test_metadata_comment_key_ignored(self, tmp_path):
        """Keys starting with '_' should be skipped."""
        data = {
            "_comment": "This is a comment",
            "stream_cs2": {
                "keywords": ["stream cs2"],
                "intent": "stream",
                "game": "cs2",
                "actions": ["launch_game"],
            },
        }
        path = tmp_path / "cmds.json"
        path.write_text(json.dumps(data))
        reg = CommandRegistry(registry_path=str(path))
        assert "_comment" not in reg.list_commands()
        assert "stream_cs2" in reg.list_commands()


# ---------------------------------------------------------------------------
# get_command
# ---------------------------------------------------------------------------

class TestGetCommand:
    def test_returns_definition_for_known_command(self, registry):
        defn = registry.get_command("stream_cs2")
        assert defn is not None
        assert "keywords" in defn

    def test_returns_none_for_unknown_command(self, registry):
        assert registry.get_command("nonexistent") is None
