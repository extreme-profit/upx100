import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from email.mime.image import MIMEImage
from pathlib import Path
from django.db import transaction
from django.utils import timezone
from django.core import signing
from django.urls import reverse
from django.template.loader import render_to_string

from .models import EmailNotification

logger = logging.getLogger(__name__)


def cancellation_url(booking):
    token = signing.dumps({'booking_id': booking.pk}, salt='client.booking.cancel')
    return settings.SITE_URL.rstrip('/') + reverse('client:booking_cancel', args=[token])


def cancellation_text(booking):
    return '\nЕсли вы передумали, пожалуйста, нажмите сюда для отмены записи:\n' + cancellation_url(booking)


def queue_email(key, recipient, subject, body):
    notification, _ = EmailNotification.objects.get_or_create(
        key=key, defaults={'recipient': recipient, 'subject': subject, 'body': body},
    )
    transaction.on_commit(lambda: deliver_email(notification.pk))
    return notification


def build_notification_message(notification):
    # Embed the local PNG so localhost/private SITE_URL does not break the logo.
    logo = None
    try:
        path = finders.find('img/logo.png')
        if path:
            data = Path(path).read_bytes()
        else:
            with staticfiles_storage.open('img/logo.png', 'rb') as source:
                data = source.read()
        logo = MIMEImage(data, _subtype='png')
        logo.add_header('Content-ID', '<42master-logo>')
        logo.add_header('Content-Disposition', 'inline', filename='logo.png')
    except (OSError, ValueError):
        # A deployment without the optional logo still sends readable emails.
        pass
    message = EmailMultiAlternatives(
        notification.subject, notification.body, settings.DEFAULT_FROM_EMAIL,
        [notification.recipient],
    )
    message.attach_alternative(render_to_string('emails/notification.html', {
        'subject': notification.subject, 'body': notification.body,
        'site_url': settings.SITE_URL.rstrip('/'),
        'logo_url': 'cid:42master-logo' if logo else '',
    }), 'text/html')
    if logo:
        message.mixed_subtype = 'related'
        message.attach(logo)
    return message


def deliver_email(pk):
    with transaction.atomic():
        notification = EmailNotification.objects.select_for_update().get(pk=pk)
        if notification.sent_at or notification.cancelled_at:
            return True
        if notification.key.endswith(':review-invitation'):
            from .models import Booking
            booking_id = notification.key.split(':')[1]
            if not Booking.objects.filter(pk=booking_id, status__in=['confirmed', 'completed'], review__isnull=True).exists():
                notification.cancelled_at = timezone.now()
                notification.save(update_fields=['cancelled_at'])
                return True
        notification.attempts += 1
        try:
            message = build_notification_message(notification)
            delivered = message.send(fail_silently=False)
            if delivered != 1:
                raise RuntimeError('Почтовый сервер не принял письмо')
        except Exception as exc:
            notification.last_error = type(exc).__name__
            logger.warning('Письмо %s не отправлено: %s', pk, type(exc).__name__)
        else:
            notification.sent_at = timezone.now()
            notification.last_error = ''
        notification.save(update_fields=['attempts', 'last_error', 'sent_at'])
        return notification.sent_at is not None


def booking_created(booking, slot):
    from .reliability import WARNING
    company = booking.service.company
    queue_email(
        f'booking:{booking.pk}:new', company.owner.email,
        f'Новая заявка на запись: {booking.service.name}',
        f'Новая заявка №{booking.pk} на услугу «{booking.service.name}».\n'
        f'Клиент: {booking.client_name}\nТелефон: {booking.client_phone}\n'
        f'Email: {booking.client_email}\n'
        f'Дата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M} ({booking.service.company.time_zone})\n'
        f'Комментарий: {booking.notes}\n'
        + ('Осторожно: у клиента три и более отмеченных неявки за текущий месяц.\n' if booking.no_show_count >= 3 else '') +
        f'Примите или отклоните заявку в личном кабинете: '
        f'{settings.SITE_URL.rstrip("/")}/business/bookings/',
    )
    if booking.client_email:
        queue_email(
            f'booking:{booking.pk}:registered', booking.client_email,
            f'Заявка успешно зарегистрирована: {booking.service.name}',
            f'{booking.client_name}, ваша заявка №{booking.pk} успешно зарегистрирована. '
            f'Ожидайте ответа от менеджера.\nУслуга: {booking.service.name}\n'
            f'Компания: {company.name}\nДата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M} ({booking.service.company.time_zone})'
            + cancellation_text(booking) + ('\n' + WARNING if booking.no_show_count >= 3 else ''),
        )


def booking_decided(booking, slot=None):
    if not booking.client_email:
        return  # Старые заявки могли быть созданы без email.
    decision = 'принята' if booking.status == 'confirmed' else 'отклонена'
    appointment = (
        f'\nДата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M} ({booking.service.company.time_zone})'
        if slot else ''
    )
    queue_email(
        f'booking:{booking.pk}:{booking.status}', booking.client_email,
        f'Заявка {decision}: {booking.service.name}',
        f'{booking.client_name}, ваша заявка №{booking.pk} на услугу '
        f'«{booking.service.name}» {decision}.\nКомпания: {booking.service.company.name}.'
        f'\nАдрес компании: {booking.service.company.address}\nФормат: {booking.service.get_delivery_mode_display()}'
        f'{appointment}' + (f'\nПричина отказа: {booking.rejection_reason}' if booking.status == 'cancelled' else '') + (cancellation_text(booking) if booking.status == 'confirmed' else ''),
    )
