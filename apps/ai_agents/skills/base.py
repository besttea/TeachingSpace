"""Skill base — the in-app counterpart of Claude Code skills.

A Skill is a production pipeline for one AI capability (course / exercise /
exam generation). It produces CONTENT (plain dicts); persistence stays with
the caller (commands/views) so skills stay testable and DB-free.

Contract: ``run(**params) -> dict``; ``validate(payload) -> (ok, message)``.
All model access goes through the harness (role routing + fallback chains).
"""

from abc import ABC, abstractmethod


class Skill(ABC):
    name: str = 'skill'
    description: str = ''

    @abstractmethod
    def run(self, **params) -> dict:
        """Execute the skill; return a result dict (content + meta)."""

    def validate(self, payload: dict) -> tuple[bool, str]:
        """Default validation hook (skills override where the sandbox applies)."""
        return True, ''
