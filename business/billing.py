from datetime import date, datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Booking, Company, InvoiceItem, MonthlyInvoice
from .notifications import queue_email
from .billing_notifications import notify_invoice
from .tochka import TochkaError

SERVICE_FEE = Decimal('100.00')


def next_month(month):
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


@transaction.atomic
def generate_invoice(company, period):
    """Месяц определяется по первому подтверждению в часовом поясе проекта."""
    Company.objects.select_for_update().get(pk=company.pk)
    existing = MonthlyInvoice.objects.filter(company=company, period=period).first()
    if existing:
        if existing.status == 'pending':
            notify_invoice(existing, 'created', 'Пора оплачивать комиссию за услуги')
            from .acquiring import queue_invoice_payment
            try:
                queue_invoice_payment(existing)
            except TochkaError:
                pass
        return existing
    start = timezone.make_aware(datetime.combine(period, time.min))
    end = timezone.make_aware(datetime.combine(next_month(period), time.min))
    services = list(company.services.filter(
        bookings__in=Booking.objects.filter(confirmed_at__gte=start, confirmed_at__lt=end).exclude(status='no_show'),
    ).distinct().order_by('pk'))
    if not services:
        return None
    invoice = MonthlyInvoice.objects.create(
        company=company, period=period, due_date=next_month(period).replace(day=5),
        amount=SERVICE_FEE * len(services),
        gateway_reference=f'tochka-{company.pk}-{period:%Y%m}',
    )
    InvoiceItem.objects.bulk_create([
        InvoiceItem(invoice=invoice, service=service, service_name=service.name, amount=SERVICE_FEE)
        for service in services
    ])
    notify_invoice(invoice, 'created', 'Пора оплачивать комиссию за услуги')
    from .acquiring import queue_invoice_payment
    try:
        queue_invoice_payment(invoice)
    except TochkaError:
        pass
    return invoice


def process_billing(today=None):
    today = today or timezone.localdate()
    current_month = today.replace(day=1)
    cutoff = timezone.make_aware(datetime.combine(current_month, time.min))
    # Восстанавливаем пропущенные месяцы после остановки планировщика.
    periods = set()
    for company_id, month in Booking.objects.filter(
        confirmed_at__lt=cutoff,
    ).annotate(month=TruncMonth('confirmed_at', tzinfo=timezone.get_current_timezone())).order_by().values_list(
        'service__company_id', 'month',
    ).distinct().iterator():
        periods.add((company_id, month.date()))
    for company_id, period in sorted(periods):
        generate_invoice(Company.objects.get(pk=company_id), period)

    for invoice in MonthlyInvoice.objects.filter(status='pending').select_related('company__owner'):
        # Напоминания догоняют пропущенный запуск, но не создаются задним числом после оплаты.
        reminder_month = invoice.due_date.replace(day=1)
        if today < reminder_month:
            continue
        urgent = today >= reminder_month.replace(day=3)
        if not urgent:
            key, subject = 'first', 'Пора оплатить услуги'
            warning = ''
        else:
            key, subject = 'urgent', 'Срочно надо оплатить услуги'
            warning = '\nЕсли счёт не будет оплачен в срок, администратор может применить санкции: скрыть ваши услуги.'
        if today > invoice.due_date:
            notify_invoice(invoice, 'overdue', 'Просрочена оплата комиссии за услуги', 'Срок оплаты истёк. Оплатите счёт; администратор может применить санкции.')
        elif urgent:
            notify_invoice(invoice, 'urgent', 'Срочно оплатите комиссию за услуги', warning.strip())
        else:
            notify_invoice(invoice, 'created', 'Пора оплачивать комиссию за услуги')
        queue_email(
            f'invoice:{invoice.pk}:{key}', invoice.company.owner.email, subject,
            f'Счёт за {invoice.period:%m.%Y}: {invoice.amount} ₽.\n'
            f'Начислено по 100 ₽ за каждую услугу с подтверждённой заявкой.\n'
            f'Оплатите до {invoice.due_date:%d.%m.%Y} включительно.{warning}\n'
            f'Счёт доступен в личном кабинете.',
        )


@transaction.atomic
def reconcile_no_show_invoice(booking):
    from django.db.models import Sum
    from .models import NoShowReport, EmailNotification
    booking.refresh_from_db(fields=['status'])
    if not booking.confirmed_at:
        return
    period = timezone.localdate(booking.confirmed_at).replace(day=1)
    invoice = MonthlyInvoice.objects.select_for_update().filter(company=booking.service.company, period=period).first()
    if not invoice:
        return
    start = timezone.make_aware(datetime.combine(period, time.min))
    end = timezone.make_aware(datetime.combine(next_month(period), time.min))
    eligible = Booking.objects.filter(service=booking.service, confirmed_at__gte=start, confirmed_at__lt=end).exclude(status='no_show').exists()
    item_exists = invoice.items.filter(service=booking.service).exists()
    if invoice.status == 'paid':
        NoShowReport.objects.filter(booking__service=booking.service, booking__confirmed_at__gte=start, booking__confirmed_at__lt=end, dismissed_at__isnull=True).update(paid_invoice_adjustment=item_exists and not eligible)
        if item_exists and not eligible:
            notify_invoice(invoice, f'paid-adjustment:{booking.pk}', 'Нужна корректировка оплаченной комиссии', 'Сумма оплаченного счёта не изменена. Администратор проверит корректировку или возврат.')
        return
    if eligible:
        InvoiceItem.objects.get_or_create(invoice=invoice, service=booking.service, defaults={'service_name':booking.service.name,'amount':SERVICE_FEE})
    else:
        invoice.items.filter(service=booking.service).delete()
    old_amount = invoice.amount
    invoice.amount = invoice.items.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    invoice.status = 'pending' if invoice.amount else 'void'
    invoice.save(update_fields=['amount','status'])
    notify_invoice(invoice, f'adjustment:{booking.pk}:{booking.status}', 'Счёт на комиссию аннулирован' if invoice.status == 'void' else 'Счёт на комиссию скорректирован', 'Актуальная сумма и состав учтённых броней указаны в этом уведомлении. Изменение связано с проверкой неявки.')
    if invoice.amount != old_amount:
        EmailNotification.objects.filter(key__startswith=f'invoice:{invoice.pk}:', sent_at__isnull=True).update(cancelled_at=timezone.now())
        queue_email(f'invoice:{invoice.pk}:adjustment:{booking.pk}:{invoice.amount}', invoice.company.owner.email,
            'Счёт скорректирован после проверки неявки',
            f'Счёт за {invoice.period:%m.%Y}: актуальная сумма {invoice.amount} ₽. '
            f'Статус: {invoice.get_status_display()}. Изменение связано с отметкой неявки по заявке №{booking.pk}.')
