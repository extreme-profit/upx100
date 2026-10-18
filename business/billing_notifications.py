from collections import defaultdict
from datetime import datetime, time
from django.utils import timezone
from django.db import transaction
from .models import BillingNotification, Booking, MonthlyInvoice


def invoice_breakdown(invoice):
    from .billing import next_month, SERVICE_FEE
    items = list(invoice.items.order_by('pk'))
    start = timezone.make_aware(datetime.combine(invoice.period, time.min))
    end = timezone.make_aware(datetime.combine(next_month(invoice.period), time.min))
    bookings = Booking.objects.filter(
        service_id__in=[item.service_id for item in items],
        confirmed_at__gte=start, confirmed_at__lt=end,
    ).exclude(status='no_show').select_related('employee__user').prefetch_related('time_slots__employee__user')
    counts = defaultdict(lambda: defaultdict(int))
    names = {}
    for booking in bookings:
        employee = booking.employee
        if employee is None:
            # Legacy bookings may still have an assigned slot, but no employee snapshot.
            slots = list(booking.time_slots.all())
            employee = slots[0].employee if slots else None
        employee_id = employee.pk if employee else None
        names[employee_id] = employee.name if employee else 'Сотрудник не указан'
        counts[booking.service_id][employee_id] += 1
    lines = [f'Расчётный месяц: {invoice.period:%m.%Y}',
             'Использования — подтверждённые брони за расчётный месяц. Неявки исключены.', '']
    for item in items:
        lines.append(f'{item.service_name}:')
        for employee_id, count in sorted(counts[item.service_id].items(), key=lambda row: names[row[0]].casefold()):
            lines.append(f'— {names[employee_id]} — количество использований: {count}')
        if not counts[item.service_id]:
            lines.append('— Нет учтённых броней; требуется проверить корректировку счёта.')
        lines.append('')
    lines.extend([f'Итого: {len(items)} × {SERVICE_FEE:.0f} = {invoice.amount:.2f} ₽',
                  f'Статус счёта: {invoice.get_status_display()}',
                  f'Срок оплаты: {invoice.due_date:%d.%m.%Y} включительно.'])
    return '\n'.join(lines)


@transaction.atomic
def notify_invoice(invoice, event, title, note=''):
    invoice = MonthlyInvoice.objects.select_for_update().get(pk=invoice.pk)
    if event in ('created', 'urgent', 'overdue') and invoice.status != 'pending':
        return None
    key = f'invoice:{invoice.pk}:{event}'
    # Existing notifications are historical snapshots, including their read state.
    existing = BillingNotification.objects.filter(key=key).first()
    if existing:
        return existing
    body = invoice_breakdown(invoice)
    if note:
        body += '\n\n' + note
    notification, _ = BillingNotification.objects.get_or_create(key=key, defaults={
        'recipient_id': invoice.company.owner_id, 'invoice': invoice, 'title': title, 'body': body,
    })
    return notification
