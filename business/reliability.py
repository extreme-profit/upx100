import ipaddress
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Booking, NoShowReport

WARNING = 'Вы попали в список ненадёжных клиентов из-за частых отмеченных неявок. Мастер вправе отказать в бронировании. Для оспаривания статуса напишите в поддержку: info@upx100.ru.'


def normalized_phone(value):
    value = re.sub(r'\D', '', value or '')
    if len(value) == 11 and value.startswith('8'):
        value = '7' + value[1:]
    return value


def client_ip(request):
    # Forwarded headers are untrusted without a configured trusted proxy.
    try:
        return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except ValueError:
        return None


def monthly_no_shows(visitor_id=None, email='', phone='', now=None):
    now = now or timezone.now()
    zone = ZoneInfo('Europe/Moscow')
    month = timezone.localdate(now, zone).replace(day=1)
    end = month.replace(year=month.year+1, month=1) if month.month == 12 else month.replace(month=month.month+1)
    identity = Q(pk__in=[])
    if visitor_id:
        identity |= Q(booking__visitor_id=visitor_id)
    email = email.strip().casefold()
    phone = normalized_phone(phone)
    if email:
        identity |= Q(booking__normalized_email=email)
    if phone:
        identity |= Q(booking__normalized_phone=phone)
    return NoShowReport.objects.filter(identity, dismissed_at__isnull=True,
        booking__appointment_at__gte=datetime.combine(month, time.min, tzinfo=zone),
        booking__appointment_at__lt=datetime.combine(end, time.min, tzinfo=zone)).count()


@transaction.atomic
def report_no_show(booking_id, company, actor):
    from .models import Company
    Company.objects.select_for_update().get(pk=company.pk)
    booking = Booking.objects.select_for_update().get(pk=booking_id, service__company=company)
    if booking.status == 'no_show':
        return booking, False
    if booking.status != 'confirmed' or not booking.appointment_end_at or booking.appointment_end_at > timezone.now():
        raise ValidationError('Неявку можно отметить только после окончания подтверждённой записи.')
    if NoShowReport.objects.filter(booking=booking).exists():
        raise ValidationError('Эта отметка уже рассмотрена администратором.')
    booking.normalized_email = booking.client_email.strip().casefold()
    booking.normalized_phone = normalized_phone(booking.client_phone)
    booking.status = 'no_show'
    booking.save(update_fields=['status', 'updated_at', 'normalized_email', 'normalized_phone'])
    NoShowReport.objects.create(booking=booking, reported_by=actor)
    from .billing import reconcile_no_show_invoice
    reconcile_no_show_invoice(booking)
    if booking.client_email:
        from .notifications import queue_email
        warning = WARNING if booking.no_show_count >= 3 else 'Если вы присутствовали или не согласны с отметкой, напишите в поддержку: info@upx100.ru.'
        queue_email(f'booking:{booking.pk}:no-show', booking.client_email, 'Исполнитель отметил неявку по записи',
            f'По заявке №{booking.pk} на услугу «{booking.service.name}» исполнитель сообщил, что клиент не пришёл.\n{warning}')
    return booking, True


@transaction.atomic
def dismiss_no_show(report_id, actor, reason):
    reason = reason.strip()
    if not reason or len(reason) > 1000:
        raise ValidationError('Укажите причину отмены отметки (до 1000 символов).')
    report = NoShowReport.objects.select_for_update().select_related('booking').get(pk=report_id)
    if report.dismissed_at:
        return
    report.dismissed_at = timezone.now()
    report.dismissed_by = actor
    report.dismissal_reason = reason
    report.save(update_fields=['dismissed_at', 'dismissed_by', 'dismissal_reason'])
    Booking.objects.filter(pk=report.booking_id, status='no_show').update(status='confirmed')
    from .billing import reconcile_no_show_invoice
    reconcile_no_show_invoice(report.booking)
    NoShowReport.objects.filter(pk=report.pk).update(paid_invoice_adjustment=False)
