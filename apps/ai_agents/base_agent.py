import os
import json
import logging
import re
import time
import hashlib

import anthropic
from django.conf import settings
from django.core.cache import cache
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

#: Cache TTL for identical prompt/model generations (seconds).
_CACHE_TTL = 24 * 3600


class AICostLimitExceeded(Exception):
    """Raised when the daily AI cost limit (AI_COST_LIMIT_DAILY) is reached."""


class BaseAgent(ABC):
    """
    Base class for all AI agents in the system.
    Handles API client initialization, error handling, and common utilities.
    """

    def __init__(self):
        # Multi-provider config: whichever provider is active (anthropic /
        # deepseek / ...) supplies key, base_url and default model.
        from .ai_config import api_key as _api_key, base_url as _base_url, model_name as _model_name

        self.api_key = _api_key()
        self.model = _model_name()
        self.max_tokens = getattr(settings, 'AI_MAX_TOKENS', 4096)
        self.temperature = getattr(settings, 'AI_TEMPERATURE', 0.7)

        if not self.api_key:
            logger.warning("No AI API key configured for the active provider.")

        # Honor the provider's base URL (DeepSeek's Anthropic-compatible
        # endpoint, custom proxies, etc.) — without it a non-official key
        # fails auth.
        client_kwargs = {'api_key': self.api_key}
        if _base_url():
            client_kwargs['base_url'] = _base_url()
        self.client = anthropic.Anthropic(**client_kwargs)

    def generate(self, prompt, system_prompt=None, temperature=None, max_tokens=None):
        """
        Generate content using the Anthropic API.

        Args:
            prompt (str): The user prompt
            system_prompt (str): Optional system prompt to set context
            temperature (float): Optional override for temperature
            max_tokens (int): Optional override for max tokens

        Returns:
            str: The generated content
        """
        kwargs = {
            "model": self.model,
            # `or` swallows falsy values like temperature=0 — use is None
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        # Response cache (optional, AI_CACHE_ENABLED): identical prompt+model
        # within the TTL returns the cached generation without an API call.
        cache_key = None
        if getattr(settings, 'AI_CACHE_ENABLED', False):
            digest = hashlib.sha256(
                f'{self.model}|{system_prompt or ""}|{prompt}'.encode('utf-8')
            ).hexdigest()
            cache_key = f'ai_gen:{digest}'
            cached = cache.get(cache_key)
            if cached:
                return cached

        # Daily cost limit (optional, AI_COST_LIMIT_DAILY)
        from .models import daily_cost_exceeded
        if daily_cost_exceeded():
            raise AICostLimitExceeded('Daily AI cost limit reached')

        start = time.time()
        input_tokens = output_tokens = 0
        try:
            try:
                response = self.client.messages.create(**kwargs)
            except anthropic.APIError as first_error:
                # Some models (e.g. DeepSeek deepseek-reasoner) reject the
                # temperature parameter entirely — retry once without it.
                if 'temperature' in str(first_error).lower() and 'temperature' in kwargs:
                    logger.warning(
                        'model %s rejected temperature; retrying without it',
                        self.model)
                    kwargs.pop('temperature')
                    response = self.client.messages.create(**kwargs)
                else:
                    raise

            # Join all text blocks (don't assume content[0] is text).
            # Reasoning models (e.g. DeepSeek deepseek-reasoner/flash) emit
            # ThinkingBlocks first — those have no .text and are skipped.
            def _text_of(resp):
                text = "".join(b.text for b in resp.content if b.type == 'text')
                if not text:
                    for b in reversed(resp.content):
                        candidate = getattr(b, 'text', None)
                        if candidate:
                            text = candidate
                            break
                return text

            text = _text_of(response)
            if not text:
                # Some reasoning models burn the entire output budget on
                # thinking when a temperature is set — retry once without it.
                if 'temperature' in kwargs:
                    logger.warning(
                        'model %s returned no text with temperature set; '
                        'retrying without it', self.model)
                    kwargs.pop('temperature')
                    response = self.client.messages.create(**kwargs)
                    text = _text_of(response)
            if not text:
                raise ValueError(
                    '模型未返回文本内容（推理模型可能把输出预算耗尽在思考上）——'
                    '可换用非推理模型（如 deepseek-chat）或降低提示长度')

            usage = getattr(response, 'usage', None)
            if usage is not None:
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens

            from .models import record_generation
            record_generation(
                agent=self.__class__.__name__,
                model=self.model,
                prompt=prompt,
                response=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=int((time.time() - start) * 1000),
                success=True,
            )
        except anthropic.APIError as e:
            from .models import record_generation
            record_generation(
                agent=self.__class__.__name__, model=self.model,
                prompt=prompt, duration_ms=int((time.time() - start) * 1000),
                success=False, error=str(e),
            )
            logger.error(f"Anthropic API Error: {str(e)}")
            raise
        except Exception as e:
            from .models import record_generation
            record_generation(
                agent=self.__class__.__name__, model=self.model,
                prompt=prompt, duration_ms=int((time.time() - start) * 1000),
                success=False, error=str(e),
            )
            logger.error(f"Unexpected error in AI generation: {str(e)}")
            raise

        if cache_key:
            cache.set(cache_key, text, _CACHE_TTL)
        return text

    def generate_json(self, prompt, system_prompt=None, max_tokens=None):
        """
        Generate structured JSON content.
        Forces the model to output JSON and parses the result.

        Args:
            max_tokens: optional output budget override (small for structure
                requests, large for content requests).
        """
        json_prompt = f"{prompt}\n\nPlease respond with valid JSON only, without any markdown formatting or explanations."

        response_text = self.generate(
            json_prompt, system_prompt, temperature=0.2, max_tokens=max_tokens)

        try:
            return self._extract_json(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {response_text[:500]}")
            error = ValueError(f"AI did not return valid JSON: {str(e)}")
            error.response_text = response_text  # let callers fall back to raw text
            raise error

    @staticmethod
    def _extract_json(text: str):
        """Locate the first complete JSON value in the model response.

        Robust against ```json fences, preamble prose, trailing explanations
        and models that drop the outer wrapper (emitting a bare sequence of
        objects, e.g. ``{...},{...}`` instead of ``{"cells": [...]}``).
        """
        if not text:
            raise json.JSONDecodeError('empty response', '', 0)
        fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        text = text.strip()
        decoder = json.JSONDecoder()

        # 1) the whole response is one JSON value
        try:
            obj, end = decoder.raw_decode(text)
            if not text[end:].strip().strip(',').strip():
                return obj
        except json.JSONDecodeError:
            pass

        # 2) a bare sequence of objects: wrap in a list
        for wrapped in ('[' + text + ']',
                        '[' + text.rstrip(',').rstrip() + ']'):
            try:
                obj, end = decoder.raw_decode(wrapped)
                if isinstance(obj, list):
                    return obj
            except json.JSONDecodeError:
                continue

        # 3) first complete object or array anywhere in the text
        for index, char in enumerate(text):
            if char not in '{[':
                continue
            try:
                obj, _end = decoder.raw_decode(text[index:])
                return obj
            except json.JSONDecodeError:
                continue
        raise json.JSONDecodeError('no JSON object found', text[:200], 0)

    @abstractmethod
    def process_request(self, request_data):
        """
        Abstract method to be implemented by specific agents.
        """
        pass
