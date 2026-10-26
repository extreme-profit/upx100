from datetime import date, datetime, timedelta
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from .models import Company, Service, Employee, Booking, BillingNotification
from .billing import generate_invoice, process_billing
from .reliability import report_no_show


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BillingBellTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('bell-owner@example.com',role='entrepreneur')
        self.company=Company.objects.create(owner=self.owner,name='Компания',is_verified=True)
        self.first=Service.objects.create(company=self.company,name='Стрижка',price=5000)
        self.second=Service.objects.create(company=self.company,name='Маникюр',price=2000)
        self.employee=Employee.objects.create(company=self.company,user=User.objects.create_user('bell-master@example.com',role='employee',first_name='Мастер один'))
        self.other=Employee.objects.create(company=self.company,user=User.objects.create_user('bell-other@example.com',role='employee',first_name='Мастер два'))
        self.at=timezone.make_aware(datetime(2026,9,15,12))
        self.bookings=[]
        for service,employee in [(self.first,self.employee),(self.first,self.employee),(self.first,self.other),(self.second,self.employee)]:
            self.bookings.append(Booking.objects.create(service=service,employee=employee,client_name='Клиент',client_phone='123',client_email='client@example.com',status='confirmed',confirmed_at=self.at,appointment_at=self.at,appointment_end_at=self.at+timedelta(hours=1)))
        Booking.objects.create(service=self.first,employee=self.employee,client_name='Неявка',client_phone='234',status='no_show',confirmed_at=self.at)

    def test_breakdown_counts_and_flat_fee_per_service(self):
        invoice=generate_invoice(self.company,date(2026,9,1))
        notification=BillingNotification.objects.get()
        self.assertIn('Стрижка:',notification.body)
        self.assertIn('Маникюр:',notification.body)
        self.assertIn('Мастер один — количество использований: 2',notification.body)
        self.assertIn('Мастер два — количество использований: 1',notification.body)
        self.assertIn('Итого: 2 × 100 = 200.00 ₽',notification.body)
        self.assertEqual(invoice.amount,200)
        generate_invoice(self.company,date(2026,9,1))
        self.assertEqual(BillingNotification.objects.count(),1)

    def test_reminders_and_read_state_are_not_duplicated(self):
        process_billing(date(2026,10,1))
        notification=BillingNotification.objects.get()
        notification.read_at=timezone.now()
        notification.save()
        process_billing(date(2026,10,1))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(BillingNotification.objects.count(),1)
        process_billing(date(2026,10,3))
        process_billing(date(2026,10,3))
        process_billing(date(2026,10,6))
        self.assertEqual(BillingNotification.objects.count(),3)
        invoice=notification.invoice
        self.assertEqual(BillingNotification.objects.count(),3)

    def test_bell_and_ownership_read_actions_with_csrf(self):
        invoice=generate_invoice(self.company,date(2026,9,1))
        notification=BillingNotification.objects.get()
        self.client.force_login(self.owner)
        response=self.client.get('/business/invoices/')
        self.assertContains(response,'billing-bell')
        self.assertEqual(response.context['billing_unread_count'],1)
        response=self.client.get(reverse('business:notification_list'))
        self.assertContains(response,'Мастер один')
        read=reverse('business:notification_read',args=[notification.pk])
        self.assertEqual(self.client.get(read).status_code,405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(read).status_code,403)
        self.assertRedirects(self.client.post(read,{'open_invoice':'1'}),reverse('business:invoice_detail',args=[invoice.pk]))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        stranger=User.objects.create_user('bell-stranger@example.com',role='entrepreneur')
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(read).status_code,404)
        self.assertNotContains(self.client.get(reverse('business:notification_list')),'Мастер один')
        self.client.force_login(self.employee.user)
        self.assertEqual(self.client.get(reverse('business:notification_list')).status_code,403)

    def test_adjustment_and_all_read_preserve_snapshot(self):
        invoice=generate_invoice(self.company,date(2026,9,1))
        original=BillingNotification.objects.get()
        original_body=original.body
        report_no_show(self.bookings[-1].pk,self.company,self.owner)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount,100)
        adjustment=BillingNotification.objects.exclude(pk=original.pk).get()
        self.assertIn('Итого: 1 × 100 = 100.00 ₽',adjustment.body)
        original.refresh_from_db()
        self.assertEqual(original.body,original_body)
        self.client.force_login(self.owner)
        self.client.post(reverse('business:notifications_read_all'))
        self.assertFalse(BillingNotification.objects.filter(read_at__isnull=True).exists())
