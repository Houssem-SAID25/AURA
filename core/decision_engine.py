"""
core/decision_engine.py
=======================
Thin orchestrator that wires the AI reasoning pipeline together.

Pipeline::

    raw text
        ↓  IntentEngine.analyze()
    intent dict
        ↓  ContextEngine.probe()
    context state  (+ optional follow-up question)
        ↓  TaskPlanner.plan()
    action list
        ↓  ActionHandler.execute()
    voice response string

The ``DecisionEngine`` is an **opt-in upgrade** to the existing two-stage
``CommandParser`` + ``ActionHandler`` pipeline.  It is activated by setting::

    "voice": { "ai_reasoning": true }

in ``config.json``.  When disabled, the assistant falls back to the
original :class:`~core.command_parser.CommandParser` path automatically.

When the intent confidence is below :data:`CONFIDENCE_THRESHOLD`, or when
``IntentEngine`` returns ``None``, the engine transparently falls back to
the legacy :class:`~core.command_parser.CommandParser` so no utterances are
silently dropped.

Usage (via session)::

    from core.session import create_session
    session = create_session(config)          # ai_reasoning flag read from config
    response = session.decision_engine.process("AURA stream valorant")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.i18n import t

logger = logging.getLogger(__name__)

# Minimum intent confidence to use the AI pipeline instead of falling back.
CONFIDENCE_THRESHOLD = 0.50


class DecisionEngine:
    """
    Orchestrates the IntentEngine → ContextEngine → TaskPlanner → ActionHandler
    pipeline.

    Parameters
    ----------
    config:
        Validated application config dict.
    legacy_parser:
        A :class:`~core.command_parser.CommandParser` instance used as
        fallback when the AI pipeline cannot determine the intent.
    handler:
        A :class:`~core.action_handler.ActionHandler` instance used to
        execute planned actions.
    profile:
        Optional user profile dict (from ``config/user_profile.json``).
        Passed to :class:`~core.context_engine.ContextEngine`.
    """

    def __init__(
        self,
        config: dict,
        legacy_parser: Any,
        handler: Any,
        profile: Optional[dict] = None,
    ) -> None:
        self._config = config
        self._legacy_parser = legacy_parser
        self._handler = handler
        self._profile = profile or {}

        # Lazy-initialise heavy sub-engines to keep session startup fast
        self._intent_engine: Optional[Any] = None
        self._context_engine: Optional[Any] = None
        self._task_planner: Optional[Any] = None

        logger.info("DecisionEngine initialised (ai_reasoning=true).")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, text: str) -> str:
        """
        Process raw speech *text* through the full AI pipeline.

        Falls back to the legacy ``CommandParser`` path when:

        * The intent confidence is below :data:`CONFIDENCE_THRESHOLD`.
        * ``IntentEngine`` returns ``None``.
        * A follow-up question is generated (context is incomplete).

        Parameters
        ----------
        text:
            Raw transcribed speech (may still contain "AURA" prefix).

        Returns
        -------
        str
            Human-readable voice response.
        """
        if not text or not text.strip():
            return t("responses.not_caught")

        # ── 1. Intent analysis ────────────────────────────────────────────
        intent_engine = self._get_intent_engine()
        intent_data = intent_engine.analyze(text)

        if intent_data is None or intent_data.get("confidence", 0) < CONFIDENCE_THRESHOLD:
            logger.debug(
                "DecisionEngine: low confidence – falling back to legacy parser."
            )
            return self._legacy_fallback(text)

        # ── 2. Context probe ──────────────────────────────────────────────
        context_engine = self._get_context_engine()
        context = context_engine.probe(intent_data)

        if context.get("follow_up"):
            logger.debug(
                "DecisionEngine: context incomplete – returning follow-up question."
            )
            return context["follow_up"]

        # ── 3. Task planning ──────────────────────────────────────────────
        task_planner = self._get_task_planner()
        actions = task_planner.plan(intent_data, context)

        # ── 4. Execution ─────────────────────────────────────────────────
        command = self._build_command(intent_data, actions)
        return self._handler.execute(command, raw_text=text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_command(self, intent_data: dict, actions: list[str]) -> dict:
        """Construct an ``ActionHandler``-compatible command dict."""
        intent = intent_data.get("intent", "")
        game = intent_data.get("game", "")
        scene = intent_data.get("scene", "")
        raw = intent_data.get("raw", "")

        if len(actions) == 1:
            # Single action – use type-based dispatch
            return {
                "type": actions[0],
                "game": game,
                "scene": scene,
                "raw": raw,
                "source": "decision_engine",
            }

        # Multi-action – use actions list for sequence execution
        return {
            "type": intent,
            "actions": actions,
            "game": game,
            "scene": scene,
            "raw": raw,
            "source": "decision_engine",
        }

    def _legacy_fallback(self, text: str) -> str:
        """Fall back to the two-stage CommandParser + ActionHandler path."""
        try:
            command = self._legacy_parser.parse(text)
            if command is None:
                return "Sorry, I didn't understand that command."
            return self._handler.execute(command, raw_text=text)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Legacy fallback error: %s", exc, exc_info=True)
            return "Something went wrong. Please check the logs."

    # ------------------------------------------------------------------
    # Lazy engine accessors
    # ------------------------------------------------------------------

    def _get_intent_engine(self) -> Any:
        if self._intent_engine is None:
            from core.intent_engine import IntentEngine  # noqa: PLC0415
            self._intent_engine = IntentEngine(self._config)
        return self._intent_engine

    def _get_context_engine(self) -> Any:
        if self._context_engine is None:
            from core.context_engine import ContextEngine  # noqa: PLC0415
            obs = getattr(self._handler, "obs", None)
            self._context_engine = ContextEngine(self._config, self._profile, obs)
        return self._context_engine

    def _get_task_planner(self) -> Any:
        if self._task_planner is None:
            from core.task_planner import TaskPlanner  # noqa: PLC0415
            self._task_planner = TaskPlanner(self._config)
        return self._task_planner
