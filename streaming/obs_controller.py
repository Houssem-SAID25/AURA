"""
streaming/obs_controller.py
============================
Backward-compatible re-export of :class:`~integrations.obs_controller.OBSController`.

The OBS controller implementation lives in ``integrations/obs_controller.py``
(alongside the other integration modules).  This module re-exports it under
the ``streaming/`` namespace so that code referencing
``streaming.obs_controller.OBSController`` continues to work.

Prefer importing from ``integrations.obs_controller`` in new code.
"""

from integrations.obs_controller import OBSController  # noqa: F401

__all__ = ["OBSController"]
