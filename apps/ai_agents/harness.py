"""AI Harness — the execution core of the platform's agent system.

Modeled on the DeepSeek-harness pattern (the same one Claude Code runs on
here): one Anthropic-compatible endpoint, multiple MODEL ROLES mapped onto
it, per-role fallback chains, and one client factory.

Roles (settings.AI_MODEL_ROLES, env AI_*_MODEL):
- ``planner``: reasoning-heavy structure work (course outlines, question
  type distributions) — default deepseek-reasoner when available, else the
  provider default;
- ``worker``: bulk content generation (lesson cells, exercises, questions)
  — default deepseek-flash (fast, cheap);
- ``grader``: evaluation (essay scoring, validation feedback) — default
  deepseek-flash.

Every call goes through ``HarnessCore.call()``, which owns ALL the
reasoning-model compatibility behaviour: temperature rejection retry,
ThinkingBlock skipping, thinking-budget retry, JSON extraction, and the
per-role fallback chain (settings.AI_FALLBACK_MODELS).
"""

import json
import logging
import re
import time

import anthropic
from django.conf import settings

from . import ai_config

logger = logging.getLogger(__name__)

#: Cache of anthropic clients keyed by (model, base_url) — one per config.
_clients: dict = {}


class HarnessError(Exception):
    """Raised when every model in the fallback chain fails.

    ``last_text`` carries the last model's raw text (when any) so callers
    can degrade gracefully (e.g. markdown-splitting fallback).
    """

    def __init__(self, message, last_text=''):
        super().__init__(message)
        self.last_text = last_text


class HarnessCore:
    """Model-role routing + fallback chains + one-shot calls."""

    # -- role/model resolution ----------------------------------------------

    @staticmethod
    def role_model(role: str) -> str:
        """Model name for a role (planner/worker/grader).

        Unset roles fall back to the active provider model — never hardcode
        a reasoning model as the planner default.
        """
        roles = getattr(settings, 'AI_MODEL_ROLES', {}) or {}
        default = ai_config.model_name()
        if role == 'planner':
            return roles.get('planner') or _first_set(
                getattr(settings, 'AI_PLANNER_MODEL', ''), default)
        if role == 'grader':
            return roles.get('grader') or _first_set(
                getattr(settings, 'AI_GRADER_MODEL', ''), default)
        return roles.get('worker') or _first_set(
            getattr(settings, 'AI_WORKER_MODEL', ''), default)

    @staticmethod
    def fallback_chain(model: str) -> list:
        """[model] + settings.AI_FALLBACK_MODELS (deduped), provider default last."""
        chain = [model]
        extra = getattr(settings, 'AI_FALLBACK_MODELS', '') or ''
        for name in extra.split(','):
            name = name.strip()
            if name and name not in chain:
                chain.append(name)
        default = ai_config.model_name()
        if default not in chain:
            chain.append(default)
        return chain

    @staticmethod
    def client_for(model: str):
        """One Anthropic client per (model, base_url) combo."""
        base_url = ai_config.base_url()
        key = (model, base_url)
        if key not in _clients:
            kwargs = {'api_key': ai_config.api_key()}
            if base_url:
                kwargs['base_url'] = base_url
            _clients[key] = anthropic.Anthropic(**kwargs)
        return _clients[key]

    # -- one-shot call with all reasoning-model compatibility ---------------

    @classmethod
    def call(cls, prompt, *, role='worker', system_prompt=None, temperature=None,
             max_tokens=None, json_mode=False):
        """Run the role's model (with fallback chain); return the text.

        Raises HarnessError if every model in the chain fails.
        """
        errors = []
        last_text = ''
        for model in cls.fallback_chain(cls.role_model(role)):
            raw = ''
            try:
                raw = cls._call_model(
                    model, prompt, system_prompt=system_prompt,
                    temperature=temperature, max_tokens=max_tokens)
                if not raw.strip():
                    raise ValueError('模型未返回文本内容（推理模型可能耗尽输出预算）')
                if json_mode:
                    return cls._extract_json(raw)
                return raw
            except (anthropic.APIError, ValueError, json.JSONDecodeError) as e:
                errors.append(f'{model}: {e}')
                logger.warning('harness model %s failed (%s) — trying next', model, e)
                if raw:  # keep the last non-empty raw text for caller fallbacks
                    last_text = raw
        raise HarnessError('所有模型均失败: ' + ' | '.join(errors), last_text)

    @classmethod
    def _call_model(cls, model, prompt, system_prompt, temperature, max_tokens):
        client = cls.client_for(model)
        kwargs = {
            'model': model,
            'max_tokens': max_tokens or int(getattr(settings, 'AI_MAX_TOKENS', 4096)),
            'messages': [{'role': 'user', 'content': prompt}],
        }
        if system_prompt:
            kwargs['system'] = system_prompt
        if temperature is not None:
            kwargs['temperature'] = temperature

        start = time.time()
        response = None
        try:
            try:
                response = client.messages.create(**kwargs)
            except anthropic.APIError as first_error:
                # Models like deepseek-reasoner reject temperature outright
                if 'temperature' in str(first_error).lower() and 'temperature' in kwargs:
                    logger.warning('model %s rejected temperature; retrying without', model)
                    kwargs.pop('temperature')
                    response = client.messages.create(**kwargs)
                else:
                    raise

            text = cls._text_of(response)
            if not text.strip() and 'temperature' in kwargs:
                # Reasoning models sometimes burn the whole budget on thinking
                # when temperature is set — retry once without it.
                logger.warning('model %s returned no text; retrying without temperature', model)
                kwargs.pop('temperature')
                response = client.messages.create(**kwargs)
                text = cls._text_of(response)

            # Audit trail (reuse the existing generation history)
            try:
                from .models import record_generation
                usage = getattr(response, 'usage', None)
                record_generation(
                    agent=f'harness:{model}', model=model, prompt=prompt,
                    response=text[:4000],
                    input_tokens=getattr(usage, 'input_tokens', 0) if usage else 0,
                    output_tokens=getattr(usage, 'output_tokens', 0) if usage else 0,
                    duration_ms=int((time.time() - start) * 1000), success=True)
            except Exception:  # never let auditing break the call
                logger.exception('record_generation failed')

            return text
        except Exception as e:
            try:
                from .models import record_generation
                record_generation(
                    agent=f'harness:{model}', model=model, prompt=prompt,
                    duration_ms=int((time.time() - start) * 1000),
                    success=False, error=str(e))
            except Exception:
                pass
            raise

    @staticmethod
    def _text_of(response) -> str:
        """Join text blocks, skipping ThinkingBlocks (reasoning models)."""
        text = ''.join(b.text for b in response.content if b.type == 'text')
        if not text:
            for b in reversed(response.content):
                candidate = getattr(b, 'text', None)
                if candidate:
                    return candidate
        return text

    @staticmethod
    def _extract_json(text: str):
        """First complete JSON value anywhere (fences/prose/sequences OK)."""
        if not text:
            raise json.JSONDecodeError('empty response', '', 0)
        fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        text = text.strip()
        decoder = json.JSONDecoder()
        try:
            obj, end = decoder.raw_decode(text)
            if not text[end:].strip().strip(',').strip():
                return obj
        except json.JSONDecodeError:
            pass
        for wrapped in ('[' + text + ']', '[' + text.rstrip(',').rstrip() + ']'):
            try:
                obj, _end = decoder.raw_decode(wrapped)
                if isinstance(obj, list):
                    return obj
            except json.JSONDecodeError:
                continue
        for index, char in enumerate(text):
            if char not in '{[':
                continue
            try:
                obj, _end = decoder.raw_decode(text[index:])
                return obj
            except json.JSONDecodeError:
                continue
        raise json.JSONDecodeError('no JSON object found', text[:200], 0)


def _first_set(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ''
