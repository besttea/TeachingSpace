"""Template filters for the training app forms."""

from django import template

register = template.Library()


@register.filter
def dict_lookup(d, key):
    """Safe dict lookup with string coercion (used by exercise form hints)."""
    try:
        return d.get(str(key), '')
    except (AttributeError, TypeError):
        return ''
