"""
Custom template tags and filters for CodeNova portal.
"""
from django import template

register = template.Library()


@register.filter
def get_options(question):
    """Return list of (letter, text) tuples for a Question instance."""
    return [
        ("A", question.option_a),
        ("B", question.option_b),
        ("C", question.option_c),
        ("D", question.option_d),
    ]


@register.filter
def options(question):
    return get_options(question)


@register.simple_tag
def progress_color(value):
    """Return a CSS class based on progress percentage."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "text-on-surface-variant"
    if v >= 75:
        return "text-secondary"
    elif v >= 50:
        return "text-primary"
    else:
        return "text-error"
