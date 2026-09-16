"""BaseAgent — thin compatibility layer over the AI Harness.

Every agent call now routes through HarnessCore (role-based model routing,
per-role fallback chains, reasoning-model compatibility). The public API
stays stable (generate / generate_json), so existing agents and callers
keep working unchanged; pass ``role='planner'|'worker'|'grader'`` to pick
the harness model role.
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from abc import ABC, abstractmethod

from .harness import HarnessCore, HarnessError

logger = logging.getLogger(__name__)

_CACHE_TTL = 24 * 3600


class AICostLimitExceeded(Exception):
    """Raised when the daily AI cost limit (AI_COST_LIMIT_DAILY) is reached."""


class BaseAgent(ABC):
    """
    Base class for all AI agents in the system.
    Handles API client initialization, error handling, and common utilities.
    """

    def __init__(self):
        from . import ai_config

        self.api_key = ai_config.api_key()
        self.model = ai_config.model_name()
        self.max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4096)
        self.temperature = getattr(settings, 'AI_TEMPERATURE', 0.7)

        if not self.api_key:
            logger.warning("No AI API key configured for the active provider.")

        # Kept for compatibility: an anthropic client for the default model.
        self.client = HarnessCore.client_for(self.model)

    def generate(self, prompt, system_prompt=None, temperature=None,
                 max_tokens=None, role='worker'):
        """
        Generate content through the harness.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt to set context
            temperature: Optional override for temperature
            max_tokens: Optional override for max tokens
            role: harness model role ('planner'|'worker'|'grader')

        Returns:
            str: The generated content
        """
        from .models import daily_cost_exceeded
        if daily_cost_exceeded():
            raise AICostLimitExceeded('Daily AI cost limit reached')

        # Response cache (optional, AI_CACHE_ENABLED)
        cache_key = None
        if getattr(settings, 'AI_CACHE_ENABLED', False):
            digest = hashlib.sha256(
                f'{role}|{system_prompt or ""}|{prompt}'.encode('utf-8')
            ).hexdigest()
            cache_key = f'ai_gen:{digest}'
            cached = cache.get(cache_key)
            if cached:
                return cached

        try:
            text = HarnessCore.call(
                prompt, role=role, system_prompt=system_prompt,
                temperature=temperature, max_tokens=max_tokens)
        except HarnessError as e:
            logger.error('Harness call failed: %s', e)
            raise ValueError(str(e))

        if cache_key:
            cache.set(cache_key, text, _CACHE_TTL)
        return text

    def generate_json(self, prompt, system_prompt=None, max_tokens=None,
                      role='worker'):
        """
        Generate structured JSON content through the harness.

        Args:
            max_tokens: optional output budget override.
            role: harness model role ('planner'|'worker'|'grader').
        """
        json_prompt = (f"{prompt}\n\nPlease respond with valid JSON only, "
                       f"without any markdown formatting or explanations.")

        from .models import daily_cost_exceeded
        if daily_cost_exceeded():
            raise AICostLimitExceeded('Daily AI cost limit reached')

        try:
            return HarnessCore.call(
                json_prompt, role=role, system_prompt=system_prompt,
                temperature=0.2, max_tokens=max_tokens, json_mode=True)
        except HarnessError as e:
            logger.error(f"Failed to parse JSON response: {str(e)[:500]}")
            error = ValueError(f"AI did not return valid JSON: {str(e)}")
            error.response_text = getattr(e, 'last_text', '')
            raise error

    @staticmethod
    def _extract_json(text: str):
        """Kept for compatibility — the harness owns extraction now."""
        return HarnessCore._extract_json(text)

    @abstractmethod
    def process_request(self, request_data):
        """
        Abstract method to be implemented by specific agents.
        """
        pass
