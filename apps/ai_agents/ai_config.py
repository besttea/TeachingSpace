"""AI model/provider selection — multi-provider support.

Providers are declared in ``settings.AI_PROVIDERS``; the active one is
chosen via ``settings.AI_PROVIDER`` (env: ``AI_PROVIDER``). Every provider
is Anthropic-API-compatible (DeepSeek exposes an Anthropic-compatible
endpoint at https://api.deepseek.com/anthropic), so one SDK client serves
all of them — only key/base_url/model change.

Examples (.env):
    AI_PROVIDER=anthropic                  # default; uses ANTHROPIC_API_KEY
    AI_PROVIDER=deepseek                   # uses the deepseek_Api env var
    AI_MODEL=deepseek-reasoner             # optional model override
"""

from django.conf import settings


def providers() -> dict:
    return getattr(settings, 'AI_PROVIDERS', {}) or {}


def active_provider() -> dict:
    """The currently selected provider dict (falls back to anthropic)."""
    name = provider_name()
    return providers().get(name) or providers().get('anthropic') or {}


def provider_name() -> str:
    return getattr(settings, 'AI_PROVIDER', 'anthropic')


def api_key() -> str:
    """API key of the active provider (e.g. from the deepseek_Api env var)."""
    return active_provider().get('api_key', '') or ''


def base_url() -> str:
    """Base URL of the active provider ('' = official endpoint)."""
    return active_provider().get('base_url', '') or ''


def model_name() -> str:
    """Model to use: settings.AI_MODEL override, else the provider default."""
    return getattr(settings, 'AI_MODEL', '') or active_provider().get('default_model', '')


def is_configured() -> bool:
    """Whether the active provider has an API key."""
    return bool(api_key())
