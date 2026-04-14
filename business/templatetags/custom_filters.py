from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Разбивает строку на список по указанному разделителю"""
    if not value:
        return []
    return value.split(arg)

@register.filter
def format_hour(value):
    """Форматирует час в двухзначный формат (0-23 -> 00-23)"""
    try:
        hour = int(value)
        return f"{hour:02d}"
    except (ValueError, TypeError):
        return value
