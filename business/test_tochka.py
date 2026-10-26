from datetime import date, datetime
from unittest.mock import patch
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from .models import Company, Service, Booking, AcquiringPayment, BillingNotification
from .billing import generate_invoice
from .acquiring import process_invoice_payment, check_payment, recover_payment
from .tochka import TochkaClient, TochkaError


@override_settings(TOCHKA_ENVIRONMENT='live',TOCHKA_LIVE_ENABLED=True,TOCHKA_JWT_TOKEN='test-only',TOCHKA_CUSTOMER_CODE='300000092',TOCHKA_MERCHANT_ID='200000000001056',TOCHKA_RECEIPT_MODE='none')
class TochkaPaymentTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('tochka-owner@example.com',role='entrepreneur')
        company=Company.objects.create(owner=self.owner,name='Компания',is_verified=True)
        service=Service.objects.create(company=company,name='Стрижка',price=3000)
        Booking.objects.create(service=service,client_name='Клиент',client_phone='123',status='confirmed',confirmed_at=timezone.make_aware(datetime(2026,9,10)))
        self.invoice=generate_invoice(company,date(2026,9,1))
        self.payment=self.invoice.acquiring_payments.get()

    def operation(self, **changes):
        data={'operationId':'bank-operation','paymentLinkId':str(self.payment.pk),'customerCode':'300000092','merchantId':'200000000001056','amount':'100.00','status':'APPROVED','paymentLink':'https://bank.example/payment'}
        data.update(changes)
        return {'Operation':[data]}

    def ready(self):
        self.payment.operation_id='bank-operation'
        self.payment.state='ready'
        self.payment.save()

    def test_create_payload_and_persistent_identity_no_double_post(self):
        with patch.object(TochkaClient,'request',return_value={'operationId':'bank-operation','paymentLink':'https://bank.example/payment','amount':'100.00','status':'CREATED'}) as request:
            process_invoice_payment(self.invoice)
            method,path,body=request.call_args.args
            self.assertEqual(method,'POST')
            self.assertEqual(path,'/acquiring/v1.0/payments')
            self.assertEqual(body['Data']['amount'],'100.00')
            self.assertEqual(body['Data']['paymentLinkId'],str(self.payment.pk))
            self.assertEqual(body['Data']['preAuthorization'],False)
        with patch.object(TochkaClient,'request',return_value=self.operation(status='CREATED')) as request:
            process_invoice_payment(self.invoice)
            self.assertEqual(request.call_args.args[0],'GET')
        self.assertEqual(AcquiringPayment.objects.count(),1)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'pending')

    def test_verified_payment_idempotent_and_not_authorized_or_partial(self):
        self.ready()
        for status in ['AUTHORIZED','WAIT_FULL_PAYMENT','CREATED']:
            with patch.object(TochkaClient,'info',return_value=self.operation(status=status)):
                check_payment(self.payment.pk)
            self.invoice.refresh_from_db()
            self.assertEqual(self.invoice.status,'pending')
        with patch.object(TochkaClient,'info',return_value=self.operation()):
            check_payment(self.payment.pk)
            self.invoice.refresh_from_db()
            paid_at=self.invoice.paid_at
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'paid')
        self.assertEqual(self.invoice.paid_payment_id,self.payment.pk)
        self.assertEqual(self.invoice.paid_at,paid_at)
        self.assertEqual(BillingNotification.objects.filter(key=f'invoice:{self.invoice.pk}:paid').count(),1)

    def test_bank_identity_amount_and_sandbox_fixture_cannot_pay(self):
        self.ready()
        for changes in [{'amount':'200.00'},{'paymentLinkId':'wrong'},{'merchantId':'wrong'},{'customerCode':'wrong'},{'operationId':'wrong'}]:
            with self.subTest(changes=changes), patch.object(TochkaClient,'info',return_value=self.operation(**changes)):
                check_payment(self.payment.pk)
                self.invoice.refresh_from_db()
                self.assertEqual(self.invoice.status,'pending')
        self.payment.environment='sandbox'
        self.payment.save()
        with patch.object(TochkaClient,'info',return_value=self.operation()):
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'pending')

    def test_timeout_not_retried_and_recovered_only_from_matching_bank_order(self):
        with patch.object(TochkaClient,'create',side_effect=TochkaError('transport_or_response_error')) as create:
            process_invoice_payment(self.invoice)
            process_invoice_payment(self.invoice)
            self.assertEqual(create.call_count,1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.state,'uncertain')
        with patch.object(TochkaClient,'info',return_value=self.operation(paymentLinkId='wrong')):
            with self.assertRaises(TochkaError):
                recover_payment(self.payment.pk,'bank-operation')
        with patch.object(TochkaClient,'info',return_value=self.operation()):
            recover_payment(self.payment.pk,'bank-operation')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'paid')

    def test_changed_amount_does_not_get_paid_and_creates_review_flag(self):
        self.ready()
        self.invoice.amount=Decimal('200')
        self.invoice.save()
        with patch.object(TochkaClient,'info',return_value=self.operation()):
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'pending')
        self.assertTrue(self.invoice.payment_review_required)

    def test_receipt_payload_and_explicit_live_enable(self):
        with override_settings(TOCHKA_RECEIPT_MODE='bank',TOCHKA_TAX_SYSTEM='usn_income',TOCHKA_VAT_TYPE='none'), patch.object(TochkaClient,'request',return_value={}) as request:
            TochkaClient().create(self.payment)
            self.assertEqual(request.call_args.args[1],'/acquiring/v1.0/payments_with_receipt')
            data=request.call_args.args[2]['Data']
            self.assertEqual(data['Client']['email'],self.owner.email)
            self.assertEqual(data['Items'][0]['quantity'],1)
            self.assertEqual(data['Items'][0]['amount'],'100.00')
        with override_settings(TOCHKA_LIVE_ENABLED=False):
            with self.assertRaises(TochkaError):
                TochkaClient()

    def test_invoice_browser_return_and_old_stub_cannot_mark_paid(self):
        self.client.force_login(self.owner)
        url=reverse('business:invoice_detail',args=[self.invoice.pk])
        self.assertEqual(self.client.get(url,{'status':'APPROVED'}).status_code,200)
        self.assertEqual(self.client.post(url).status_code,400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status,'pending')
        with patch('business.views.process_invoice_payment'):
            self.assertEqual(self.client.post(url,{'action':'check'}).status_code,302)


    def test_refund_and_second_approved_order_require_review(self):
        self.ready()
        with patch.object(TochkaClient,'info',return_value=self.operation()):
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        first_payment=self.invoice.paid_payment_id
        with patch.object(TochkaClient,'info',return_value=self.operation(status='REFUNDED_PARTIALLY')):
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.payment_review_required)
        self.assertEqual(self.invoice.status,'paid')
        self.payment=AcquiringPayment.objects.create(invoice=self.invoice,environment='live',customer_code='300000092',merchant_id='200000000001056',amount=100,operation_id='second-operation',state='ready')
        with patch.object(TochkaClient,'info',return_value=self.operation(operationId='second-operation')):
            check_payment(self.payment.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_payment_id,first_payment)
        self.assertTrue(self.invoice.payment_review_required)
