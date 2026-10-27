"""
Run via manage.py shell; ACTION is supplied through runpy.init_globals.


Создать первый счёт, отправить письмо и уведомление в колокольчик
python manage.py shell -c "import runpy; runpy.run_path('demo_billing.py', init_globals={'ACTION': 'create'})"

Создать для него операцию в песочнице Точки
python manage.py shell -c "import runpy; runpy.run_path('demo_billing.py', init_globals={'ACTION': 'sandbox'})"

Имитировать оплату первого счёта
python manage.py shell -c "import runpy; runpy.run_path('demo_billing.py', init_globals={'ACTION': 'pay'})"

Создать второй счёт и сделать его просроченным
python manage.py shell -c "import runpy; runpy.run_path('demo_billing.py', init_globals={'ACTION': 'overdue'})"

"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from business.models import Company, MonthlyInvoice, InvoiceItem
from business.billing_notifications import notify_invoice
from business.notifications import queue_email, deliver_email

COMPANY_ID = 3  # Change if necessary.
RUN = "manual-1"  # Change only to start a NEW independent demo.
action = globals().get("ACTION", "status")
if action not in {"create", "sandbox", "pay", "overdue", "status"}:
    raise ValueError("ACTION: create, sandbox, pay, overdue, status")
if settings.TOCHKA_ENVIRONMENT != "sandbox":
    raise RuntimeError("This script requires TOCHKA_ENVIRONMENT=sandbox")

company = Company.objects.select_related("owner").get(pk=COMPANY_ID)
prefix = f"demo-{company.pk}-{RUN}"


def reference(label):
    return f"{prefix}-{label}"


def get_invoice(label):
    return MonthlyInvoice.objects.get(gateway_reference=reference(label))


def create_invoice(label):
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company.pk)
        existing = MonthlyInvoice.objects.filter(gateway_reference=reference(label)).first()
        if existing:
            return existing
        service = company.services.order_by("pk").first()
        if service is None:
            raise ValueError("Add at least one service to the company first")
        period = timezone.localdate().replace(day=1)
        while MonthlyInvoice.objects.filter(company=company, period=period).exists():
            period = (period - timedelta(days=1)).replace(day=1)
        invoice = MonthlyInvoice.objects.create(
            company=company, period=period,
            due_date=timezone.localdate() + timedelta(days=7),
            amount=Decimal("100.00"), gateway_reference=reference(label),
        )
        InvoiceItem.objects.create(
            invoice=invoice, service=service,
            service_name=service.name, amount=Decimal("100.00"),
        )
        return invoice


def announce(invoice, event, title, note):
    notify_invoice(invoice, event, title, note)
    url = f"{settings.SITE_URL.rstrip('/')}/business/invoices/{invoice.pk}/"
    email = queue_email(
        f"demo:{invoice.pk}:{event}", company.owner.email, title,
        f"{note}\nСчёт №{invoice.pk}: {invoice.amount} ₽.\n"
        f"Срок оплаты: {invoice.due_date:%d.%m.%Y} включительно.\n{url}",
    )
    email.refresh_from_db()
    if not email.sent_at:
        deliver_email(email.pk)
        email.refresh_from_db()
    print("Email accepted by backend:", bool(email.sent_at), "Error:", email.last_error)


print("Company:", company.pk, company.name)
print("Recipient:", company.owner.email)
print("Email backend:", settings.EMAIL_BACKEND)

if action == "create":
    invoice = create_invoice("first")
    if invoice.status != "pending":
        raise ValueError("First invoice is no longer pending; use status")
    announce(invoice, "created", "ТЕСТ: сформирован счёт на комиссию",
             "Демонстрационный счёт. Реальная комиссия не начислялась.")

elif action == "sandbox":
    from business.acquiring import process_invoice_payment
    invoice = get_invoice("first")
    if invoice.status != "pending":
        raise ValueError("Create a pending first invoice before this action")
    payment = process_invoice_payment(invoice)
    if payment is None:
        raise RuntimeError("No payment attempt was created")
    print("Payment:", payment.pk, "State:", payment.state)
    print("Operation:", payment.operation_id, "Error:", payment.last_error)

elif action == "pay":
    with transaction.atomic():
        invoice = MonthlyInvoice.objects.select_for_update().get(
            gateway_reference=reference("first"))
        if invoice.status not in ("pending", "paid"):
            raise ValueError("Invoice is void")
        if invoice.status == "pending":
            invoice.status = "paid"
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at"])
    announce(invoice, "paid", "ТЕСТ: комиссия оплачена",
             "Оплата имитирована через консоль. Банк оплату не подтверждал, деньги не списывались.")

elif action == "overdue":
    invoice = create_invoice("second")
    if invoice.status != "pending":
        raise ValueError("Second invoice is no longer pending")
    announce(invoice, "created", "ТЕСТ: сформирован второй счёт",
             "Демонстрационный счёт для проверки просрочки.")
    invoice.due_date = timezone.localdate() - timedelta(days=1)
    invoice.save(update_fields=["due_date"])
    announce(invoice, "overdue", "ТЕСТ: просрочена оплата комиссии",
             "Срок оплаты истёк. Администратор может применить санкции. Это тестовое уведомление.")

for invoice in MonthlyInvoice.objects.filter(
        gateway_reference__in=[reference("first"), reference("second")]):
    print("Invoice:", invoice.pk, "Status:", invoice.status,
          "Amount:", invoice.amount, "Due:", invoice.due_date,
          "Overdue:", invoice.is_overdue)
    print(f"{settings.SITE_URL.rstrip('/')}/business/invoices/{invoice.pk}/")
