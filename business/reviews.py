from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from .models import Booking, Review
from .notifications import queue_email


def can_review(booking, now=None):
    return bool(booking.employee_id and booking.appointment_end_at
                and booking.status in ('confirmed', 'completed')
                and booking.appointment_end_at <= (now or timezone.now()))


def review_url(booking):
    return settings.SITE_URL.rstrip('/') + reverse('client:booking_review', args=[booking.review_token])


@transaction.atomic
def save_review(booking_id, rating, comment):
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if not can_review(booking):
        return None
    review, _ = Review.objects.get_or_create(booking=booking, defaults={
        'employee_id': booking.employee_id, 'rating': rating, 'comment': comment,
    })
    return review


def process_review_invitations(now=None):
    now = now or timezone.now()
    bookings = Booking.objects.filter(
        status__in=['confirmed', 'completed'], employee__isnull=False,
        appointment_end_at__lte=now-timedelta(hours=24), review__isnull=True,
    ).exclude(client_email='').select_related('service', 'employee__user')
    for booking in bookings.iterator():
        queue_email(
            f'booking:{booking.pk}:review-invitation', booking.client_email,
            'Услуга оказана — оставьте отзыв о мастере',
            f'{booking.client_name}, как прошла услуга «{booking.service.name}»?\n'
            f'Мастер: {booking.employee.name}\n'
            'Оставьте оценку и отзыв. Это поможет другим клиентам выбрать специалиста.\n'
            f'Оставить отзыв: {review_url(booking)}',
        )
