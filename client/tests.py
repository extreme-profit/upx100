from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from business.models import Company, Employee, Service, ServiceTimeSlot


class ServiceWeekTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('weeks@example.com', role='entrepreneur')
        company = Company.objects.create(owner=owner, name='Салон', address='Москва', is_verified=True)
        self.service = Service.objects.create(company=company, name='Стрижка', price=100)
        employee_user = User.objects.create_user('specialist@example.com', role='employee')
        self.employee = Employee.objects.create(company=company, user=employee_user)
        self.service.employees.add(self.employee)
        self.today = timezone.datetime(2026, 12, 29).date()
        self.url = reverse('client:service_detail', args=[self.service.pk])
        for offset in [0, 1, 2, 6, 7, 20]:
            ServiceTimeSlot.objects.create(
                service=self.service, employee=self.employee,
                date=self.today + timedelta(days=offset), start_time=time(12), end_time=time(13),
            )

    def page(self, params=None):
        with patch('client.views.timezone.localdate', return_value=self.today), patch(
            'client.views.timezone.now', return_value=timezone.make_aware(datetime(2026, 12, 29, 9)),
        ):
            return self.client.get(self.url, params or {})

    def test_dates_and_seven_day_boundaries(self):
        response = self.page()
        self.assertContains(response, 'Сегодня, 29.12.2026')
        self.assertContains(response, 'Завтра, 30.12.2026')
        self.assertContains(response, '31.12.2026')
        self.assertEqual(list(response.context['slots_by_date']), [
            self.today + timedelta(days=n) for n in [0, 1, 2, 6]
        ])
        second = self.page({'week': 2})
        self.assertEqual(list(second.context['slots_by_date']), [self.today + timedelta(days=7)])
        self.assertNotContains(second, 'Сегодня,')
        self.assertEqual(second.context['week_start'], self.today + timedelta(days=7))

    def test_employee_filter_and_last_page(self):
        response = self.page({'week': 2, 'employee_id': self.employee.pk})
        self.assertContains(response, f'?week=3&amp;employee_id={self.employee.pk}')
        last = self.page({'week': 3})
        self.assertFalse(last.context['week_page'].has_next())
        self.assertEqual(list(last.context['slots_by_date']), [self.today + timedelta(days=20)])

    def test_empty_week_and_invalid_page(self):
        ServiceTimeSlot.objects.filter(date=self.today + timedelta(days=7)).delete()
        self.assertContains(self.page({'week': 2}), 'На выбранной неделе нет свободного времени')
        self.assertEqual(self.page({'week': 'invalid'}).context['week_page'].number, 1)
        self.assertEqual(self.page({'week': '999999999999999999999'}).context['week_page'].number, 3)


class CompanyTimezoneTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('tz-owner@example.com', role='entrepreneur')
        self.company = Company.objects.create(owner=owner, name='Владивосток', time_zone='Asia/Vladivostok', is_verified=True)
        self.service = Service.objects.create(company=self.company, name='Встреча', price=100)

    def test_today_and_booking_follow_company_timezone(self):
        from datetime import timezone as utc_timezone
        from business.booking_workflow import create_booking
        from django.core.exceptions import ValidationError
        now = datetime(2026, 10, 18, 20, tzinfo=utc_timezone.utc)  # 19 October, 06:00 locally.
        past = ServiceTimeSlot.objects.create(service=self.service, date=now.date() + timedelta(days=1), start_time=time(5), end_time=time(6))
        future = ServiceTimeSlot.objects.create(service=self.service, date=now.date() + timedelta(days=1), start_time=time(7), end_time=time(8))
        with patch('django.utils.timezone.now', return_value=now):
            response = self.client.get(reverse('client:service_detail', args=[self.service.pk]))
            self.assertEqual(response.context['week_start'], future.date)
            self.assertContains(response, 'Сегодня, 19.10.2026')
            self.assertContains(response, 'Asia/Vladivostok')
            self.assertEqual(list(response.context['slots_by_date'].values())[0], [future])
            data = dict(slot_id=past.pk, client_name='Клиент', client_phone='123', client_email='client-tz@example.com', notes='')
            with self.assertRaises(ValidationError):
                create_booking(self.service.pk, data)
            data['slot_id'] = future.pk
            booking = create_booking(self.service.pk, data)
            self.assertEqual(booking.service_id, self.service.pk)

    def test_timezone_validation_and_dst(self):
        from business.forms import CompanyForm
        from business.timezones import slot_start
        from django.core.exceptions import ValidationError
        form = CompanyForm(data={'name':'Компания','address':'Адрес','time_zone':'invalid/zone'})
        self.assertFalse(form.is_valid())
        self.assertIn('time_zone', form.errors)
        self.company.time_zone = 'Europe/Berlin'
        self.company.save()
        for day, hour in [(timezone.datetime(2026, 3, 29).date(), 2), (timezone.datetime(2026, 10, 25).date(), 2)]:
            slot = ServiceTimeSlot(service=self.service, date=day, start_time=time(hour, 30), end_time=time(4))
            with self.assertRaises(ValidationError):
                slot_start(slot)


class VisitorHistoryTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('history-owner@example.com', role='entrepreneur')
        company = Company.objects.create(owner=owner, name='История', address='Улица, 5', is_verified=True)
        self.service = Service.objects.create(company=company, name='Секретная услуга', price=100)
        self.slot = ServiceTimeSlot.objects.create(service=self.service, date=timezone.localdate()+timedelta(days=2), start_time=time(12), end_time=time(13))

    def test_history_cookie_isolation_and_cancellation_keeps_date(self):
        from django.test import Client
        from business.models import Booking
        from business.booking_workflow import cancel_client_booking
        response = self.client.post(reverse('client:booking_create', args=[self.service.pk]), {
            'slot_id':self.slot.pk, 'client_name':'Имя', 'client_phone':'123', 'client_email':'visitor@example.com', 'notes':'',
        })
        self.assertEqual(response.status_code, 302)
        cookie = self.client.cookies['booking_visitor']
        self.assertTrue(cookie['httponly'])
        booking = Booking.objects.get()
        self.assertIsNotNone(booking.visitor_id)
        self.assertIsNotNone(booking.appointment_at)
        url = reverse('client:booking_history')
        self.assertContains(self.client.get(url), self.service.name)
        self.assertNotContains(Client().get(url), self.service.name)
        stranger = Client()
        stranger.cookies['booking_visitor'] = str(booking.visitor_id)  # Unsigned forgery.
        self.assertNotContains(stranger.get(url), self.service.name)
        cancel_client_booking(booking.pk)
        self.assertNotContains(self.client.get(url), self.service.name)
        self.assertContains(self.client.get(url, {'tab':'past'}), self.service.name)
        self.assertContains(self.client.get(url, {'tab':'past'}), 'Отменено клиентом')

    def test_delivery_mode_search_filter(self):
        from unittest.mock import patch
        remote = Service.objects.create(company=self.service.company, name='Удалённая консультация', price=100, delivery_mode='remote')
        response = self.client.get('/search/', {'delivery_mode':'remote'})
        self.assertContains(response, remote.name)
        self.assertNotContains(response, self.service.name)
