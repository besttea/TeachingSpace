"""Template filters for safe embedding of cell data into JS."""

from django import template
from django.utils.html import escapejs

register = template.Library()


@register.filter
def escapejs_tick(value):
    r"""escapejs + escape ` and ${ so the result is safe inside JS template literals.

    Django's escapejs does not escape backticks, and a backtick (or a ``${``
    interpolation) inside a template literal breaks out of the string and
    injects into the surrounding Alpine expression / script. Encoding both
    sequences as \uXXXX keeps them as inert string content.
    """
    escaped = escapejs(value or '')
    return escaped.replace('`', '\\u0060').replace('${', '\\u0024{')
