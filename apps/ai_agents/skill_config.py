"""Skill-level tunable parameters — the harness architecture's adjustment
knobs (user feedback 2026-09-17: skill 参数化可调机制必须体现在 AI 设置中).

Every skill reads its knobs through :func:`skill_params` instead of
hardcoding temperature/max_tokens/caps. Three layering levels, lowest
wins over default, highest wins overall:

1. ``DEFAULTS`` (this file) — sane production defaults
2. ``AI_SKILL_PARAMS`` setting — a JSON object (set via .env, e.g.
   ``AI_SKILL_PARAMS={"exam_generation": {"max_questions": 20, "temperature": 0.5}}``)
3. per-knob env vars ``AI_SKILL_<NAME>_<KEY>`` (e.g.
   ``AI_SKILL_EXAM_GENERATION_TEMPERATURE=0.6``) — for container/task-specific
   tuning without touching .env JSON
"""

import os

from django.conf import settings

DEFAULTS = {
    'exam_generation': {
        # phase 1 (planner): question type distribution
        'plan_temperature': 0.2,
        'plan_max_tokens': 300,
        # phase 2 (worker): one request per question
        'temperature': 0.2,
        'max_tokens': 1200,
        'max_questions': 30,
        # sandbox validation of code questions before saving
        'validate_code': True,
        # near-duplicate filtering (SequenceMatcher ratio on normalized text)
        'dedup_enabled': True,
        'dedup_threshold': 0.85,
    },
    'exercise_generation': {
        'temperature': 0.2,
        'max_tokens': 1500,
        'max_fix_attempts': 2,   # sandbox-feedback regeneration loop
        'validate_code': True,
        'dedup_enabled': True,
        'dedup_threshold': 0.85,
    },
    'course_design': {
        'outline_temperature': 0.2,
        'outline_max_tokens': 800,
        'content_temperature': 0.3,
        'content_max_tokens': 1200,
        'deep_content_temperature': 0.5,
        'deep_content_max_tokens': 3000,
        'max_lessons': 30,
        'max_cells_per_lesson': 10,
    },
    'knowledge_extraction': {
        'temperature': 0.2,
        'max_tokens': 800,
        'max_points_per_chapter': 8,
        'chapter_char_cap': 6000,   # teaching text truncated before the call
        'dedup_enabled': True,
        'dedup_threshold': 0.85,
    },
}


def _cast(value: str, like):
    """Cast an env-var string to the default value's type."""
    if isinstance(like, bool):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    if isinstance(like, int):
        return int(value)
    if isinstance(like, float):
        return float(value)
    return value


def skill_params(name: str) -> dict:
    """Effective parameters for one skill (layered, see module docstring)."""
    params = dict(DEFAULTS.get(name, {}))

    configured = getattr(settings, 'AI_SKILL_PARAMS', None) or {}
    params.update(configured.get(name, {}) or {})

    env_prefix = f'AI_SKILL_{name.upper()}_'
    for key in list(params):
        raw = os.environ.get(env_prefix + key.upper())
        if raw is None:
            continue
        try:
            params[key] = _cast(raw, params[key])
        except ValueError:
            pass  # malformed override: keep the previous layer's value
    return params
