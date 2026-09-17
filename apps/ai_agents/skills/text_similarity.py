"""Shared text-similarity helpers for AI generation dedup.

Used by ExamSkill (question dedup), ExerciseSkill (batch dedup), and the
knowledge-point extraction pipeline (merge dedup) — one implementation,
same thresholds everywhere.
"""

import re

from difflib import SequenceMatcher

_WORD_RE = re.compile(r'[\W_]+', re.UNICODE)


def normalize_text(text: str) -> str:
    """Lowercased alphanumeric tokens — similarity input."""
    return _WORD_RE.sub(' ', text or '').lower()


def similarity_ratio(a: str, b: str) -> float:
    """SequenceMatcher ratio on normalized strings (0.0-1.0)."""
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def is_near_duplicate(candidate: str, existing: list, threshold: float) -> bool:
    """True when ``candidate`` is a near-duplicate of any item in ``existing``.

    ``existing`` may hold raw strings or dicts carrying the compared text
    under ``title`` (exercises/knowledge points) or ``text`` (exam
    questions). Empty candidates count as duplicates (unusable anyway).
    """
    if not normalize_text(candidate):
        return True
    for other in existing:
        if isinstance(other, dict):
            other_text = other.get('title') or other.get('text') or ''
        else:
            other_text = other
        if similarity_ratio(candidate, other_text) >= threshold:
            return True
    return False
