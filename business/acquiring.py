from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import AcquiringPayment, MonthlyInvoice
from .tochka import TochkaClient, TochkaError
from .billing_notifications import notify_invoice


def queue_invoice_payment(invoice):
    if invoice.status != 'pending' or invoice.amount <= 0:
        return None
    client = TochkaClient()
    with transaction.atomic():
        invoice = MonthlyInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != 'pending' or invoice.amount <= 0:
            return None
        existing = invoice.acquiring_payments.filter(environment=client.environment, amount=invoice.amount).exclude(state='expired').first()
        if existing:
            return existing
        return AcquiringPayment.objects.create(invoice=invoice, environment=client.environment,
            amount=invoice.amount, customer_code=client.customer, merchant_id=client.merchant)


def process_invoice_payment(invoice):
    payment = queue_invoice_payment(invoice)
    if payment is None:
        return None
    if payment.operation_id:
        check_payment(payment.pk)
        payment.refresh_from_db()
        return payment
    # Commit the durable claim before POST: a crash/timeout must not create another order.
    claimed = AcquiringPayment.objects.filter(pk=payment.pk, state='queued').update(state='creating')
    if not claimed:
        return payment
    try:
        data = TochkaClient(payment.environment).create(payment)
        operation_id, url = data.get('operationId'), data.get('paymentLink')
        if not isinstance(operation_id,str) or not operation_id or len(operation_id)>100 or not isinstance(url,str) or len(url)>2083 or urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
            raise TochkaError('invalid_create_response')
        if payment.environment == 'live' and Decimal(str(data.get('amount'))) != payment.amount:
            raise TochkaError('amount_mismatch')
        with transaction.atomic():
            AcquiringPayment.objects.filter(pk=payment.pk).update(operation_id=operation_id,payment_url=url,state='ready',bank_status=str(data.get('status','CREATED'))[:32],last_error='')
    except (TochkaError, InvalidOperation, ValueError, OSError, IntegrityError) as exc:
        # A timeout may mean that the bank DID create the order. Do not repeat POST.
        code = str(exc) if isinstance(exc,TochkaError) else 'invalid_create_response'
        AcquiringPayment.objects.filter(pk=payment.pk).update(state='queued' if code in ('receipt_mode_required','receipt_settings_missing','credentials_missing','live_disabled','http_400','http_401','http_403','http_404','http_429') else 'uncertain',last_error=code[:80])
    payment.refresh_from_db()
    return payment


def check_payment(payment_id):
    payment = AcquiringPayment.objects.select_related('invoice').get(pk=payment_id)
    if not payment.operation_id:
        return
    try:
        result = TochkaClient(payment.environment).info(payment.operation_id)
        operations = result.get('Operation', [])
        if not isinstance(operations,list):
            raise TochkaError('invalid_operations')
        operation = next((row for row in operations if isinstance(row,dict) and row.get('operationId') == payment.operation_id), None)
        if operation is None:
            raise TochkaError('operation_not_found')
        status = operation.get('status','')
        if payment.environment == 'sandbox':
            # Sandbox data are static fixtures, never evidence of an actual payment.
            AcquiringPayment.objects.filter(pk=payment.pk).update(bank_status=str(status)[:32],checked_at=timezone.now(),last_error='')
            return
        if (operation.get('customerCode') != payment.customer_code or operation.get('merchantId') != payment.merchant_id
            or operation.get('paymentLinkId') != str(payment.pk) or Decimal(str(operation.get('amount'))) != payment.amount):
            raise TochkaError('payment_identity_or_amount_mismatch')
        with transaction.atomic():
            invoice = MonthlyInvoice.objects.select_for_update().get(pk=payment.invoice_id)
            AcquiringPayment.objects.filter(pk=payment.pk).update(bank_status=str(status)[:32],checked_at=timezone.now(),last_error='',state='expired' if status=='EXPIRED' else 'ready')
            if status == 'APPROVED':
                if invoice.status == 'pending' and invoice.amount == payment.amount:
                    invoice.paid_payment=payment
                    invoice.status='paid'
                    invoice.paid_at=timezone.now()
                    invoice.save(update_fields=['status','paid_at','paid_payment'])
                    notify_invoice(invoice,'paid','Комиссия за услуги оплачена','Оплата подтверждена Точка-Банком.')
                elif invoice.status != 'paid' or invoice.amount != payment.amount or invoice.paid_payment_id != payment.pk:
                    invoice.payment_review_required=True
                    invoice.save(update_fields=['payment_review_required'])
                    notify_invoice(invoice,f'bank-mismatch:{payment.pk}','Требуется сверка поступившей оплаты','Банк подтвердил оплату прежней суммы или аннулированного счёта. Обратитесь в поддержку; автоматический зачёт не выполнен.')
            elif status in ('ON-REFUND','REFUNDED','REFUNDED_PARTIALLY'):
                invoice.payment_review_required=True
                invoice.save(update_fields=['payment_review_required'])
                notify_invoice(invoice,f'bank-refund:{payment.pk}:{status}','Банк сообщил о возврате оплаты','Требуется сверка суммы возврата администратором. Повторное начисление автоматически не выполняется.')
    except (TochkaError, InvalidOperation, ValueError, TypeError, OSError):
        AcquiringPayment.objects.filter(pk=payment.pk).update(last_error='verification_failed',checked_at=timezone.now())


def sync_payments():
    # Historical payments remain monitored after local correction/annulment.
    for payment in AcquiringPayment.objects.exclude(operation_id='').exclude(state='expired').iterator():
        if payment.environment == settings.TOCHKA_ENVIRONMENT:
            check_payment(payment.pk)
    for invoice in MonthlyInvoice.objects.filter(status='pending').iterator():
        try:
            payment = queue_invoice_payment(invoice)
            if payment and not payment.operation_id:
                process_invoice_payment(invoice)
        except TochkaError:
            continue


def recover_payment(payment_id, operation_id):
    """Operator recovery after an ambiguous POST; bank evidence is mandatory."""
    payment = AcquiringPayment.objects.get(pk=payment_id)
    data = TochkaClient(payment.environment).info(operation_id)
    try:
        operation = next((row for row in data.get('Operation',[]) if isinstance(row,dict) and row.get('operationId') == operation_id),None)
        matched = (operation and operation.get('paymentLinkId') == str(payment.pk)
                   and operation.get('customerCode') == payment.customer_code and operation.get('merchantId') == payment.merchant_id
                   and Decimal(str(operation.get('amount'))) == payment.amount)
    except (ValueError, InvalidOperation, TypeError):
        matched = False
    if not matched:
        raise TochkaError('recovery_identity_mismatch')
    url=operation.get('paymentLink','')
    if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname or len(operation_id)>100:
        raise TochkaError('recovery_response_invalid')
    try:
        with transaction.atomic():
            AcquiringPayment.objects.filter(pk=payment.pk, operation_id='').update(operation_id=operation_id,payment_url=url,state='ready',last_error='')
    except IntegrityError:
        raise TochkaError('operation_already_used') from None
    check_payment(payment.pk)
