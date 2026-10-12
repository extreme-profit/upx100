import logging

from django.conf import settings
from django.core.mail import send_mail
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


def deliver_email(pk):
    with transaction.atomic():
        notification = EmailNotification.objects.select_for_update().get(pk=pk)
        if notification.sent_at:
            return True
        notification.attempts += 1
        try:
            delivered = send_mail(
                notification.subject, notification.body, settings.DEFAULT_FROM_EMAIL,
                [notification.recipient], fail_silently=False,
                html_message=render_to_string('emails/notification.html', {
                    'subject': notification.subject, 'body': notification.body,
                    'site_url': settings.SITE_URL.rstrip('/'),
                }),
            )
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
    company = booking.service.company
    queue_email(
        f'booking:{booking.pk}:new', company.owner.email,
        f'Новая заявка на запись: {booking.service.name}',
        f'Новая заявка №{booking.pk} на услугу «{booking.service.name}».\n'
        f'Клиент: {booking.client_name}\nТелефон: {booking.client_phone}\n'
        f'Email: {booking.client_email}\n'
        f'Дата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M}\n'
        f'Комментарий: {booking.notes}\n'
        f'Примите или отклоните заявку в личном кабинете: '
        f'{settings.SITE_URL.rstrip("/")}/business/bookings/',
    )
    if booking.client_email:
        queue_email(
            f'booking:{booking.pk}:registered', booking.client_email,
            f'Заявка успешно зарегистрирована: {booking.service.name}',
            f'{booking.client_name}, ваша заявка №{booking.pk} успешно зарегистрирована. '
            f'Ожидайте ответа от менеджера.\nУслуга: {booking.service.name}\n'
            f'Компания: {company.name}\nДата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M}'
            + cancellation_text(booking),
        )


def booking_decided(booking, slot=None):
    if not booking.client_email:
        return  # Старые заявки могли быть созданы без email.
    decision = 'принята' if booking.status == 'confirmed' else 'отклонена'
    appointment = (
        f'\nДата: {slot.date:%d.%m.%Y}, время: {slot.start_time:%H:%M}'
        if slot else ''
    )
    queue_email(
        f'booking:{booking.pk}:{booking.status}', booking.client_email,
        f'Заявка {decision}: {booking.service.name}',
        f'{booking.client_name}, ваша заявка №{booking.pk} на услугу '
        f'«{booking.service.name}» {decision}.\nКомпания: {booking.service.company.name}.'
        f'{appointment}' + (cancellation_text(booking) if booking.status == 'confirmed' else ''),
    )
