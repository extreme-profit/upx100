from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
from django.core.exceptions import ValidationError


def timezone_choices():
    return [(name, name.replace('_', ' ')) for name in sorted(available_timezones())]


def slot_start(slot):
    """Wall-clock slots belong to the company; reject DST gaps/ambiguity."""
    naive = datetime.combine(slot.date, slot.start_time)
    zone = ZoneInfo(slot.service.company.time_zone)
    candidates = []
    for fold in (0, 1):
        value = naive.replace(tzinfo=zone, fold=fold)
        if value.astimezone(ZoneInfo('UTC')).astimezone(zone).replace(tzinfo=None) == naive:
            if not any(existing.utcoffset() == value.utcoffset() for existing in candidates):
                candidates.append(value)
    if len(candidates) != 1:
        raise ValidationError('Выбранное время недоступно из-за перевода часов. Выберите другое.')
    return candidates[0]
