from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Booking, Service, ServiceTimeSlot
from .notifications import booking_created, booking_decided


@transaction.atomic
def create_booking(service_id, data):
    service = Service.objects.visible().select_related('company__owner').get(pk=service_id)
    slot = ServiceTimeSlot.objects.select_for_update().get(
        pk=data['slot_id'], service=service, is_booked=False,
    )
    starts_at = timezone.make_aware(datetime.combine(slot.date, slot.start_time))
    if starts_at <= timezone.now() or (slot.employee and not slot.employee.is_active):
        raise ValidationError('Выбранное время недоступно')
    booking = Booking.objects.create(
        service=service, client_name=data['client_name'], client_phone=data['client_phone'],
        client_email=data['client_email'], notes=data['notes'],
    )
    # Условное обновление защищает от двух заявок на одно время.
    claimed = ServiceTimeSlot.objects.filter(pk=slot.pk, is_booked=False).update(
        is_booked=True, booking=booking,
    )
    if not claimed:
        raise ValidationError('Выбранное время уже занято')
    booking_created(booking, slot)
    return booking


@transaction.atomic
def decide_booking(pk, company, decision):
    booking = Booking.objects.select_for_update().select_related('service__company').get(
        pk=pk, service__company=company,
    )
    if booking.status != 'pending':
        return booking, False
    if decision not in ('confirmed', 'cancelled'):
        raise ValueError('Неизвестное решение')
    changes = {'status': decision, 'updated_at': timezone.now()}
    if decision == 'confirmed':
        changes['confirmed_at'] = timezone.now()
    updated = Booking.objects.filter(pk=pk, status='pending').update(**changes)
    if not updated:
        return booking, False
    booking.refresh_from_db()
    slot = booking.time_slots.first()
    if decision == 'cancelled':
        booking.time_slots.update(is_booked=False, booking=None)
    booking_decided(booking, slot)
    return booking, True
