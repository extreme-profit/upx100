from datetime import date, datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Booking, Company, InvoiceItem, MonthlyInvoice
from .notifications import queue_email

SERVICE_FEE = Decimal('100.00')


def next_month(month):
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


@transaction.atomic
def generate_invoice(company, period):
    """Месяц определяется по первому подтверждению в часовом поясе проекта."""
    Company.objects.select_for_update().get(pk=company.pk)
    existing = MonthlyInvoice.objects.filter(company=company, period=period).first()
    if existing:
        return existing
    start = timezone.make_aware(datetime.combine(period, time.min))
    end = timezone.make_aware(datetime.combine(next_month(period), time.min))
    services = list(company.services.filter(
        bookings__confirmed_at__gte=start, bookings__confirmed_at__lt=end,
    ).distinct().order_by('pk'))
    if not services:
        return None
    invoice = MonthlyInvoice.objects.create(
        company=company, period=period, due_date=next_month(period).replace(day=5),
        amount=SERVICE_FEE * len(services),
        gateway_reference=f'stub-{company.pk}-{period:%Y%m}',
    )
    InvoiceItem.objects.bulk_create([
        InvoiceItem(invoice=invoice, service=service, service_name=service.name, amount=SERVICE_FEE)
        for service in services
    ])
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
        queue_email(
            f'invoice:{invoice.pk}:{key}', invoice.company.owner.email, subject,
            f'Счёт за {invoice.period:%m.%Y}: {invoice.amount} ₽.\n'
            f'Начислено по 100 ₽ за каждую услугу с подтверждённой заявкой.\n'
            f'Оплатите до {invoice.due_date:%d.%m.%Y} включительно.{warning}\n'
            f'Счёт доступен в личном кабинете.',
        )


@transaction.atomic
def mark_stub_paid(invoice):
    """Заглушка эквайринга; доступ к ней контролирует HTTP-представление."""
    return MonthlyInvoice.objects.filter(pk=invoice.pk, status='pending').update(
        status='paid', paid_at=timezone.now(),
    )
