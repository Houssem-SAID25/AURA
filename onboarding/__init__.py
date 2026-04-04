"""
onboarding/__init__.py
======================
Public API for the top-level onboarding package.

Exposes :class:`OnboardingManager` which orchestrates all 8 onboarding
steps for AURA's first-launch CLI experience.

Usage::

    from onboarding import OnboardingManager

    manager = OnboardingManager()
    if manager.run():
        # profile saved; proceed to main app
        pass
"""

from onboarding.onboarding_manager import OnboardingManager  # noqa: F401

__all__ = ["OnboardingManager"]
