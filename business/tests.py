from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from companies.models import Category, Subcategory
from .billing import generate_invoice, process_billing
from .models import Booking, Company, EmailNotification, Employee, MonthlyInvoice, Service, ServiceTimeSlot
from .notifications import deliver_email


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BusinessWorkflowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner@example.com', 'password', role='entrepreneur')
        self.company = Company.objects.create(owner=self.owner, name='Салон', address='Москва', is_verified=True)
        self.category = Category.objects.create(name='Красота', slug='beauty')
        self.subcategory = Subcategory.objects.create(category=self.category, name='Волосы', slug='hair')
        self.service = Service.objects.create(
            company=self.company, name='Стрижка', price=2500, category=self.category, subcategory=self.subcategory,
        )
        self.slot = ServiceTimeSlot.objects.create(
            service=self.service, date=timezone.localdate() + timedelta(days=1),
            start_time=time(12), end_time=time(13),
        )
        self.data = {
            'slot_id': self.slot.pk, 'client_name': 'Анна', 'client_phone': '+79990000000',
            'client_email': 'client@example.com', 'notes': 'Комментарий',
        }

    def submit(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('client:booking_create', args=[self.service.pk]), self.data)
        self.assertEqual(response.status_code, 302)
        return Booking.objects.get()

    def decide(self, booking, action='confirm'):
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse(f'business:booking_{action}', args=[booking.pk]), {'rejection_reason':'Нет свободного времени'})

    def test_free_service_creation_and_public_pages(self):
        employee_user = User.objects.create_user('employee@example.com', role='employee')
        employee = Employee.objects.create(company=self.company, user=employee_user)
        self.client.force_login(self.owner)
        for name in ['Маникюр', 'Укладка']:
            response = self.client.post(reverse('business:service_create'), {
                'name': name, 'price': '500', 'description': '', 'delivery_mode': 'onsite',
                'category': self.category.pk, 'subcategory_id': self.subcategory.pk, 'employees': [employee.pk],
            })
            self.assertEqual(response.status_code, 302)
            service = Service.objects.get(name=name)
            self.assertIsNone(service.payment_due_date)
            self.assertEqual(service.status, 'active')
            self.assertContains(self.client.get('/search/'), name)
        self.assertEqual(MonthlyInvoice.objects.count(), 0)
        for url in ['/', '/search/', '/client/companies/', f'/client/company/{self.company.pk}/',
                    f'/business/company/{self.company.pk}/', f'/client/service/{self.service.pk}/',
                    '/business/profile/', '/business/invoices/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_booking_notification_and_acceptance_are_idempotent(self):
        booking = self.submit()
        self.assertEqual(booking.status, 'pending')
        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)
        self.assertEqual(self.slot.booking_id, booking.pk)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertIn('Новая заявка', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].alternatives[0][1], 'text/html')
        self.assertIn('42master', mail.outbox[0].alternatives[0][0])
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/business/bookings/'), 'Анна')
        self.assertEqual(self.decide(booking).status_code, 302)
        booking.refresh_from_db()
        confirmed_at = booking.confirmed_at
        self.assertEqual(booking.status, 'confirmed')
        self.assertIsNotNone(confirmed_at)
        self.assertEqual(mail.outbox[-1].to, [self.data['client_email']])
        self.assertIn('принята', mail.outbox[-1].subject)
        self.assertIn(self.company.address, mail.outbox[-1].body)
        self.assertIn(self.slot.date.strftime('%d.%m.%Y'), mail.outbox[-1].body)
        self.assertIn('12:00', mail.outbox[-1].body)
        self.decide(booking)
        self.decide(booking, 'cancel')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        self.assertEqual(booking.confirmed_at, confirmed_at)
        self.assertEqual(len(mail.outbox), 3)

    def test_rejection_emails_client_and_frees_slot(self):
        booking = self.submit()
        self.decide(booking, 'cancel')
        booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertIsNone(booking.confirmed_at)
        self.assertFalse(self.slot.is_booked)
        self.assertIsNone(self.slot.booking_id)
        self.assertIn('отклонена', mail.outbox[-1].subject)
        self.assertIn(self.slot.date.strftime('%d.%m.%Y'), mail.outbox[-1].body)
        self.assertIn('12:00', mail.outbox[-1].body)
        self.decide(booking, 'cancel')
        self.assertEqual(len(mail.outbox), 3)

    def test_booking_validation_and_double_booking(self):
        url = reverse('client:booking_create', args=[self.service.pk])
        for email in ['', 'invalid']:
            response = self.client.post(url, dict(self.data, client_email=email))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Booking.objects.count(), 0)
        self.submit()
        self.client.post(url, self.data)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(EmailNotification.objects.count(), 2)

    def test_past_and_foreign_slots_cannot_be_booked(self):
        url = reverse('client:booking_create', args=[self.service.pk])
        self.slot.date = timezone.localdate() - timedelta(days=1)
        self.slot.save()
        self.client.post(url, self.data)
        self.assertEqual(Booking.objects.count(), 0)
        other = Service.objects.create(company=self.company, name='Другая', price=100)
        self.slot.service = other
        self.slot.save()
        self.client.post(url, self.data)
        self.assertEqual(Booking.objects.count(), 0)

    def test_owner_only_post_decisions_with_csrf(self):
        booking = self.submit()
        url = reverse('business:booking_confirm', args=[booking.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 405)
        stranger = User.objects.create_user('stranger@example.com', role='entrepreneur')
        Company.objects.create(owner=stranger, name='Другая', address='Москва', is_verified=True)
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(url).status_code, 404)
        employee_user = User.objects.create_user('employee@example.com', role='employee')
        employee = Employee.objects.create(company=self.company, user=employee_user)
        self.service.employees.add(employee)
        self.client.force_login(employee_user)
        self.assertEqual(self.client.post(url).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')

    def test_block_hides_current_future_services_and_prevents_bookings(self):
        admin_user = User.objects.create_superuser('admin@example.com', 'password')
        self.client.force_login(admin_user)
        response = self.client.post(reverse('dashboard:user_toggle_services', args=[self.owner.pk]))
        self.assertEqual(response.status_code, 302)
        future = Service.objects.create(company=self.company, name='Будущая', price=100)
        self.assertEqual(Service.objects.visible().count(), 0)
        for url in ['/', '/search/', '/search/?q=Стрижка', '/client/companies/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            if 'services' in response.context:
                self.assertEqual(list(response.context['services']), [])
            if 'companies' in response.context:
                self.assertEqual(list(response.context['companies']), [])
        for url in [f'/client/service/{self.service.pk}/', f'/client/service/{future.pk}/',
                    f'/client/company/{self.company.pk}/', f'/business/company/{self.company.pk}/']:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('client:booking_create', args=[self.service.pk]), self.data).status_code, 404)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        owner_client = Client()
        owner_client.force_login(self.owner)
        self.assertEqual(owner_client.get('/business/invoices/').status_code, 200)
        self.client.post(reverse('dashboard:user_toggle_services', args=[self.owner.pk]))
        self.assertEqual(Service.objects.visible().count(), 2)

    def test_archival_retains_confirmed_history(self):
        booking = self.submit()
        self.decide(booking)
        self.client.post(reverse('business:service_delete', args=[self.service.pk]))
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_archived)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Service.objects.visible().count(), 0)
        with self.assertRaises(ProtectedError):
            self.service.delete()

    def test_failed_mail_is_persisted_and_retried(self):
        with patch('business.notifications.EmailMultiAlternatives.send', side_effect=OSError('SMTP unavailable')):
            booking = self.submit()
        notification = EmailNotification.objects.get(key=f'booking:{booking.pk}:new')
        self.assertIsNone(notification.sent_at)
        self.assertEqual(notification.attempts, 1)
        self.assertEqual(booking.status, 'pending')
        self.assertTrue(deliver_email(notification.pk))
        self.assertTrue(deliver_email(notification.pk))
        self.assertEqual(len(mail.outbox), 1)

    def test_success_page_does_not_expose_other_clients(self):
        booking = self.submit()
        url = reverse('client:booking_success', args=[booking.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Client().get(url).status_code, 404)

    def test_registration_and_signed_cancellation(self):
        from .notifications import cancellation_url
        booking = self.submit()
        self.assertEqual(mail.outbox[1].to, [self.data['client_email']])
        self.assertIn('Ожидайте ответа от менеджера', mail.outbox[1].body)
        url = cancellation_url(booking).split('://', 1)[1].split('/', 1)[1]
        url = '/' + url
        browser = Client()
        self.assertEqual(browser.get(url).status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(browser.post(url).status_code, 302)
        booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(booking.status, 'client_cancelled')
        self.assertFalse(self.slot.is_booked)
        self.assertIsNone(self.slot.booking_id)
        count = len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            browser.post(url)
        self.assertEqual(len(mail.outbox), count)
        self.decide(booking)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'client_cancelled')
        self.assertEqual(browser.get(url[:-2] + 'x/').status_code, 404)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url).status_code, 403)

    def test_html_notifications_escape_client_input_and_keep_links(self):
        self.data['client_name'] = '<script>alert(1)</script>'
        booking = self.submit()
        html = mail.outbox[1].alternatives[0][0]
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('/client/booking/cancel/', html)
        self.assertIn('href=', html)
        self.assertIn('Ожидайте ответа от менеджера', mail.outbox[1].body)

    def test_assigned_employee_can_confirm_and_client_can_cancel(self):
        from .notifications import cancellation_url
        employee_user = User.objects.create_user('assigned@example.com', role='employee')
        employee = Employee.objects.create(company=self.company, user=employee_user)
        self.slot.employee = employee
        self.slot.save()
        booking = self.submit()
        self.client.force_login(employee_user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('business:booking_confirm', args=[booking.pk]))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        self.assertIn(cancellation_url(booking).split('/client/')[0], mail.outbox[-1].body)
        confirmed_at = booking.confirmed_at
        from .booking_workflow import cancel_client_booking
        with self.captureOnCommitCallbacks(execute=True):
            cancel_client_booking(booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.confirmed_at, confirmed_at)
        self.assertEqual(booking.status, 'client_cancelled')

    def test_only_admin_can_block_services_and_existing_account_ban_hides_them(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('dashboard:user_toggle_services', args=[self.owner.pk]))
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_blocked)
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(Service.objects.visible().count(), 0)

    def test_unverified_company_and_archived_services_stay_hidden(self):
        self.company.is_verified = False
        self.company.save()
        self.assertEqual(Service.objects.visible().count(), 0)
        self.assertEqual(self.client.get(f'/client/service/{self.service.pk}/').status_code, 404)
        self.company.is_verified = True
        self.company.save()
        self.service.is_archived = True
        self.service.save()
        self.assertEqual(Service.objects.visible().count(), 0)

    def test_stale_vector_index_filters_blocked_services(self):
        import faiss
        import numpy as np
        from search.vector_search import search_similar

        other_owner = User.objects.create_user('other@example.com')
        other_company = Company.objects.create(owner=other_owner, name='Другая', address='Москва', is_verified=True)
        other_service = Service.objects.create(company=other_company, name='Другая услуга', price=100)
        index = faiss.IndexFlatIP(2)
        index.add(np.array([[1, 0], [0.8, 0.6]], dtype='float32'))
        self.owner.is_active = False
        self.owner.save()
        with patch('search.vector_search.load_vector_index', return_value=(index, [self.service.pk, other_service.pk], {})):
            with patch('search.vector_search.get_model') as model:
                model.return_value.encode.return_value = np.array([[1, 0]], dtype='float32')
                self.assertEqual(search_similar('услуга', top_k=1), [other_service.pk])
        other_company.is_blocked = True
        other_company.save()
        with patch('search.vector_search.load_vector_index', return_value=(index, [self.service.pk, other_service.pk], {})):
            with patch('search.vector_search.get_model') as model:
                self.assertEqual(search_similar('услуга'), [])
                model.assert_not_called()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MonthlyBillingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner@example.com', role='entrepreneur')
        self.company = Company.objects.create(owner=self.owner, name='Салон', address='Москва', is_verified=True)
        self.first = Service.objects.create(company=self.company, name='Стрижка', price=5000)
        self.second = Service.objects.create(company=self.company, name='Маникюр', price=3000)
        self.idle = Service.objects.create(company=self.company, name='Нет записей', price=100)

    def booking(self, service, at, status='confirmed'):
        return Booking.objects.create(
            service=service, client_name='Клиент', client_phone='123',
            status=status, confirmed_at=at,
        )

    def at(self, year, month, day, hour=12):
        return timezone.make_aware(datetime(year, month, day, hour))

    def process(self, day):
        with self.captureOnCommitCallbacks(execute=True):
            process_billing(day)

    def test_one_hundred_per_service_not_per_booking_or_price(self):
        self.booking(self.first, self.at(2026, 9, 1))
        self.booking(self.first, self.at(2026, 9, 30))
        self.booking(self.second, self.at(2026, 9, 15), status='completed')
        self.booking(self.idle, None, status='pending')
        self.booking(self.idle, None, status='cancelled')
        self.process(date(2026, 10, 1))
        invoice = MonthlyInvoice.objects.get()
        self.assertEqual(invoice.amount, Decimal('200'))
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.period, date(2026, 9, 1))
        self.assertEqual(invoice.due_date, date(2026, 10, 5))
        self.assertTrue(invoice.gateway_reference.startswith('tochka-'))
        self.process(date(2026, 10, 1))
        self.assertEqual(MonthlyInvoice.objects.count(), 1)
        self.assertEqual(EmailNotification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminders_on_first_and_third_only_for_unpaid(self):
        self.booking(self.first, self.at(2026, 9, 15))
        self.process(date(2026, 10, 1))
        self.assertIn('Пора оплатить', mail.outbox[-1].subject)
        self.process(date(2026, 10, 2))
        self.assertEqual(len(mail.outbox), 1)
        self.process(date(2026, 10, 3))
        self.assertIn('Срочно', mail.outbox[-1].subject)
        self.assertIn('санкции', mail.outbox[-1].body)
        self.process(date(2026, 10, 3))
        self.process(date(2026, 10, 6))
        self.assertEqual(len(mail.outbox), 2)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)  # Автоматических санкций пока нет.
        invoice = MonthlyInvoice.objects.get()
        self.client.force_login(self.owner)
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['status','paid_at'])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')
        paid_at = invoice.paid_at
        self.client.get(reverse('business:invoice_detail', args=[invoice.pk]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_at, paid_at)
        self.process(date(2026, 10, 7))
        self.assertEqual(len(mail.outbox), 2)

    def test_paid_invoice_does_not_get_urgent_reminder(self):
        self.booking(self.first, self.at(2026, 9, 15))
        self.process(date(2026, 10, 1))
        self.client.force_login(self.owner)
        MonthlyInvoice.objects.update(status='paid', paid_at=timezone.now())
        self.process(date(2026, 10, 3))
        self.assertEqual(len(mail.outbox), 1)

    def test_calendar_boundaries_use_moscow_time_and_year_rollover(self):
        self.booking(self.first, self.at(2026, 12, 31, 23))
        self.booking(self.second, self.at(2027, 1, 1, 0))
        self.process(date(2027, 1, 1))
        invoice = MonthlyInvoice.objects.get()
        self.assertEqual(invoice.period, date(2026, 12, 1))
        self.assertEqual(invoice.due_date, date(2027, 1, 5))
        self.assertEqual(invoice.amount, 100)
        self.assertEqual(invoice.items.get().service, self.first)

    def test_archive_and_block_do_not_erase_invoice(self):
        self.booking(self.first, self.at(2026, 9, 15))
        self.first.is_archived = True
        self.first.save()
        self.owner.is_active = False
        self.owner.save()
        self.process(date(2026, 10, 1))
        self.assertEqual(MonthlyInvoice.objects.get().amount, 100)

    def test_no_confirmed_bookings_means_no_invoice(self):
        self.booking(self.first, None, 'cancelled')
        self.process(date(2026, 10, 1))
        self.assertEqual(MonthlyInvoice.objects.count(), 0)
        self.assertEqual(EmailNotification.objects.count(), 0)

    def test_invoice_access_and_removed_stub(self):
        self.booking(self.first, self.at(2026, 9, 15))
        invoice = generate_invoice(self.company, date(2026, 9, 1))
        url = reverse('business:invoice_detail', args=[invoice.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        stranger = User.objects.create_user('stranger@example.com', role='entrepreneur')
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url), 'Песочница Точка-Банка')
        self.assertEqual(self.client.post(url).status_code, 400)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'pending')

    def test_overdue_starts_after_fifth_inclusive(self):
        self.booking(self.first, self.at(2026, 9, 15))
        invoice = generate_invoice(self.company, date(2026, 9, 1))
        with patch('business.models.timezone.localdate', return_value=date(2026, 10, 5)):
            self.assertFalse(invoice.is_overdue)
        with patch('business.models.timezone.localdate', return_value=date(2026, 10, 6)):
            self.assertTrue(invoice.is_overdue)

    def test_management_command_recovers_missed_months(self):
        self.booking(self.first, self.at(2026, 8, 15))
        self.booking(self.second, self.at(2026, 9, 15))
        with patch('business.billing.timezone.localdate', return_value=date(2026, 10, 3)):
            with self.captureOnCommitCallbacks(execute=True):
                with patch('business.management.commands.process_monthly_billing.sync_payments'):
                    call_command('process_monthly_billing')
        self.assertEqual(MonthlyInvoice.objects.count(), 2)
        self.assertEqual(EmailNotification.objects.count(), 2)

    def test_old_payment_link_does_not_charge_for_publication(self):
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse('business:payment_process', args=[self.first.pk])), '/business/invoices/')
        self.assertEqual(self.first.payments.count(), 0)
