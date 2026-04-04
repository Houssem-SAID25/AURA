"""
tests/test_task_planner.py
==========================
Unit tests for core/task_planner.py – TaskPlanner.
"""

import pytest
from core.task_planner import TaskPlanner, _INTENT_TO_ACTIONS


DUMMY_CONFIG = {
    "games": {"valorant": "C:\\valorant.exe"},
}


class TestTaskPlannerPlan:
    def setup_method(self):
        self.planner = TaskPlanner(DUMMY_CONFIG)

    def test_returns_list(self):
        actions = self.planner.plan({"intent": "start_stream"})
        assert isinstance(actions, list)

    def test_start_stream_single_action(self):
        actions = self.planner.plan({"intent": "start_stream"})
        assert actions == ["start_stream"]

    def test_stop_stream_single_action(self):
        actions = self.planner.plan({"intent": "stop_stream"})
        assert actions == ["stop_stream"]

    def test_gaming_stream_session_multi_action(self):
        actions = self.planner.plan({"intent": "gaming_stream_session"})
        assert "launch_game" in actions
        assert "start_stream" in actions
        assert len(actions) > 1

    def test_launch_game_single(self):
        actions = self.planner.plan({"intent": "launch_game", "game": "valorant"})
        assert actions == ["launch_game"]

    def test_launch_game_with_stream_flag_upgrades(self):
        actions = self.planner.plan(
            {"intent": "launch_game", "game": "valorant", "stream": True}
        )
        # When stream flag is set, planner upgrades to gaming_stream_session actions
        assert "start_stream" in actions

    def test_help_intent(self):
        actions = self.planner.plan({"intent": "help"})
        assert actions == ["help"]

    def test_unknown_intent_returns_help_fallback(self):
        actions = self.planner.plan({"intent": "totally_unknown_intent_xyz"})
        assert actions == ["help"]

    def test_empty_intent_returns_help_fallback(self):
        actions = self.planner.plan({"intent": ""})
        assert actions == ["help"]

    def test_trending_games(self):
        actions = self.planner.plan({"intent": "trending_games"})
        assert actions == ["trending_games"]

    def test_suggest_game(self):
        actions = self.planner.plan({"intent": "suggest_game"})
        assert actions == ["suggest_game"]

    def test_mute_mic(self):
        actions = self.planner.plan({"intent": "mute_mic"})
        assert actions == ["mute_mic"]

    def test_unmute_mic(self):
        actions = self.planner.plan({"intent": "unmute_mic"})
        assert actions == ["unmute_mic"]

    def test_switch_scene(self):
        actions = self.planner.plan({"intent": "switch_scene"})
        assert actions == ["switch_scene"]

    def test_launch_obs(self):
        actions = self.planner.plan({"intent": "launch_obs"})
        assert actions == ["launch_obs"]


class TestTaskPlannerContextPruning:
    def setup_method(self):
        self.planner = TaskPlanner(DUMMY_CONFIG)

    def test_launch_obs_pruned_when_obs_running(self):
        context = {"obs_running": True}
        actions = self.planner.plan(
            {"intent": "gaming_stream_session"}, context=context
        )
        assert "launch_obs" not in actions

    def test_launch_obs_kept_when_obs_not_running(self):
        context = {"obs_running": False}
        actions = self.planner.plan(
            {"intent": "gaming_stream_session"}, context=context
        )
        assert "launch_obs" in actions

    def test_no_context_no_pruning(self):
        actions = self.planner.plan({"intent": "gaming_stream_session"})
        assert "launch_obs" in actions

    def test_empty_context_no_pruning(self):
        actions = self.planner.plan({"intent": "gaming_stream_session"}, context={})
        assert "launch_obs" in actions


class TestTaskPlannerRegistryIntegration:
    def test_loads_registry_without_error(self):
        # Just confirm construction doesn't raise
        planner = TaskPlanner()
        assert planner is not None

    def test_registry_intent_used_when_present(self):
        # "stream" intent is in commands.json
        planner = TaskPlanner()
        actions = planner.plan({"intent": "stream", "game": "cs2"})
        # Should return the registry-defined actions, not fallback
        assert isinstance(actions, list)
        assert len(actions) > 0


class TestBuiltinIntentMap:
    def test_all_basic_intents_covered(self):
        expected = [
            "start_stream", "stop_stream", "switch_scene", "launch_obs",
            "open_twitch", "launch_game", "trending_games", "suggest_game",
            "mute_mic", "unmute_mic", "help", "gaming_stream_session",
        ]
        for intent in expected:
            assert intent in _INTENT_TO_ACTIONS, f"Missing intent: {intent}"

    def test_all_actions_are_lists(self):
        for intent, actions in _INTENT_TO_ACTIONS.items():
            assert isinstance(actions, list), f"Actions for {intent} must be a list"
            assert len(actions) > 0, f"Actions for {intent} must not be empty"
