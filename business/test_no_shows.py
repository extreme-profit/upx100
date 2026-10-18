from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core import mail
from accounts.models import User
from .models import Company, Service, Booking, NoShowReport, Employee, ServiceTimeSlot, EmailNotification
from .reliability import monthly_no_shows, report_no_show, dismiss_no_show, normalized_phone, client_ip
from .billing import generate_invoice


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NoShowTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('noshowowner@example.com',role='entrepreneur')
        self.company=Company.objects.create(owner=self.owner,name='Салон',is_verified=True)
        self.service=Service.objects.create(company=self.company,name='Услуга',price=100)
        self.visitor=uuid.uuid4()
        self.now=timezone.make_aware(datetime(2026,10,18,12))
        self.clock=patch('django.utils.timezone.now',return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def booking(self, day=10, **kwargs):
        data=dict(service=self.service, client_name='Клиент',client_phone='+7 (999) 123-45-67',client_email='Person@Example.com', visitor_id=self.visitor, status='confirmed', appointment_at=timezone.make_aware(datetime(2026,10,day,10)),appointment_end_at=timezone.make_aware(datetime(2026,10,day,11)),confirmed_at=timezone.make_aware(datetime(2026,10,1,10)))
        data.update(kwargs)
        return Booking.objects.create(**data)

    def test_three_in_month_normalization_and_dismissal(self):
        for day in [10,11,12]:
            booking=self.booking(day)
            report_no_show(booking.pk,self.company,self.owner)
        self.assertEqual(monthly_no_shows(email='person@example.com'),3)
        self.assertEqual(monthly_no_shows(phone='8 999 123 45 67'),3)
        self.assertEqual(monthly_no_shows(visitor_id=self.visitor),3)
        self.assertEqual(monthly_no_shows(email='other@example.com',phone='111'),0)
        self.assertEqual(monthly_no_shows(email='person@example.com',now=timezone.make_aware(datetime(2026,11,1))),0)
        report=NoShowReport.objects.first()
        with self.assertRaises(ValidationError):
            dismiss_no_show(report.pk,self.owner,' ')
        dismiss_no_show(report.pk,self.owner,'Клиент присутствовал, проверено звонком')
        self.assertEqual(monthly_no_shows(email='person@example.com'),2)
        report.refresh_from_db()
        self.assertIsNotNone(report.dismissed_at)

    def test_idempotent_report_and_no_premature_no_show(self):
        booking=self.booking()
        report_no_show(booking.pk,self.company,self.owner)
        report_no_show(booking.pk,self.company,self.owner)
        self.assertEqual(NoShowReport.objects.count(),1)
        future=self.booking(19)
        with self.assertRaises(ValidationError):
            report_no_show(future.pk,self.company,self.owner)
        pending=self.booking(status='pending')
        with self.assertRaises(ValidationError):
            report_no_show(pending.pk,self.company,self.owner)

    def test_pending_invoice_reconciles_and_restores(self):
        booking=self.booking()
        period=self.now.date().replace(day=1)
        invoice=generate_invoice(self.company,period)
        self.assertEqual(invoice.amount,Decimal('100'))
        report_no_show(booking.pk,self.company,self.owner)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount,0)
        self.assertEqual(invoice.status,'void')
        dismiss_no_show(NoShowReport.objects.get().pk,self.owner,'Ошибка исполнителя')
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount,100)
        self.assertEqual(invoice.status,'pending')

    def test_other_valid_booking_keeps_service_fee_and_paid_invoice_is_flagged(self):
        first=self.booking()
        other=self.booking(11)
        invoice=generate_invoice(self.company,self.now.date().replace(day=1))
        report_no_show(first.pk,self.company,self.owner)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount,100)
        invoice.status='paid'
        invoice.save()
        report_no_show(other.pk,self.company,self.owner)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount,100)
        self.assertTrue(NoShowReport.objects.get(booking=other).paid_invoice_adjustment)

    def test_report_permissions_and_required_rejection_reason(self):
        booking=self.booking()
        url=reverse('business:booking_no_show',args=[booking.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code,405)
        user=User.objects.create_user('noshowstranger@example.com',role='entrepreneur')
        Company.objects.create(owner=user,name='Другая')
        self.client.force_login(user)
        self.assertEqual(self.client.post(url).status_code,404)
        pending=self.booking(status='pending')
        self.client.force_login(self.owner)
        cancel=reverse('business:booking_cancel',args=[pending.pk])
        self.assertEqual(self.client.post(cancel).status_code,400)
        pending.refresh_from_db()
        self.assertEqual(pending.status,'pending')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(cancel,{'rejection_reason':'Не смогу принять в это время'}).status_code,302)
        self.assertIn('Не смогу принять в это время',mail.outbox[-1].body)
        self.assertEqual(Client().get(reverse('dashboard:no_show_reports')).status_code,302)

    def test_ip_not_forwarded_and_warnings_on_new_booking(self):
        request=RequestFactory().get('/',REMOTE_ADDR='192.0.2.1',HTTP_X_FORWARDED_FOR='203.0.113.8')
        self.assertEqual(client_ip(request),'192.0.2.1')
        for day in [10,11,12]:
            report_no_show(self.booking(day).pk,self.company,self.owner)
        slot=ServiceTimeSlot.objects.create(service=self.service,date=self.now.date()+timedelta(days=1),start_time=time(12),end_time=time(13))
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(reverse('client:booking_create',args=[self.service.pk]),{'slot_id':slot.pk,'client_name':'Тот же клиент','client_phone':'89991234567','client_email':'person@example.com','notes':''},REMOTE_ADDR='192.0.2.2')
        self.assertEqual(response.status_code,302)
        latest=Booking.objects.latest('pk')
        self.assertEqual(latest.client_ip,'192.0.2.2')
        self.assertEqual(latest.normalized_phone,'79991234567')
        self.assertContains(self.client.get(response.url),'список ненадёжных клиентов')
        self.assertIn('Осторожно',mail.outbox[-2].body)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/business/bookings/'),'Осторожно')
        admin=User.objects.create_superuser('noshowadmin@example.com','password')
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse('dashboard:no_show_reports')),'Person@Example.com')

    def test_no_show_excluded_from_new_invoice_and_queued_review_email(self):
        from .notifications import deliver_email
        booking=self.booking()
        notification=EmailNotification.objects.create(key=f'booking:{booking.pk}:review-invitation',recipient=booking.client_email,subject='Отзыв',body='Приглашение')
        report_no_show(booking.pk,self.company,self.owner)
        self.assertIsNone(generate_invoice(self.company,self.now.date().replace(day=1)))
        self.assertTrue(deliver_email(notification.pk))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.cancelled_at)
        self.assertIsNone(notification.sent_at)
        self.assertEqual(len(mail.outbox),0)

    def test_assigned_employee_and_admin_can_dismiss_but_not_stranger(self):
        user=User.objects.create_user('noshowemployee@example.com',role='employee')
        employee=Employee.objects.create(company=self.company,user=user)
        booking=self.booking(employee=employee)
        self.client.force_login(user)
        url=reverse('business:booking_no_show',args=[booking.pk])
        self.assertEqual(self.client.post(url).status_code,302)
        report=NoShowReport.objects.get(booking=booking)
        adminurl=reverse('dashboard:no_show_reports')
        self.assertEqual(self.client.post(adminurl,{'report_id':report.pk,'action':'dismiss','reason':'Подмена'}).status_code,302)
        report.refresh_from_db()
        self.assertIsNone(report.dismissed_at)
        admin=User.objects.create_superuser('resolveadmin@example.com','password')
        self.client.force_login(admin)
        self.assertEqual(self.client.post(adminurl,{'report_id':report.pk,'action':'dismiss','reason':'Подтверждено присутствие'}).status_code,302)
        report.refresh_from_db()
        self.assertIsNotNone(report.dismissed_at)
        self.assertEqual(report.dismissed_by_id,admin.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status,'confirmed')

    def test_no_show_removes_review_from_public_rating(self):
        from .models import Review
        user=User.objects.create_user('reviewnoshow@example.com',role='employee')
        employee=Employee.objects.create(company=self.company,user=user)
        self.service.employees.add(employee)
        booking=self.booking(employee=employee)
        Review.objects.create(booking=booking,employee=employee,rating=1,comment='Текст скрытого отзыва')
        report_no_show(booking.pk,self.company,self.owner)
        response=self.client.get(reverse('client:service_detail',args=[self.service.pk]))
        self.assertNotContains(response,'Текст скрытого отзыва')
        master=list(response.context['employees'])[0]
        self.assertEqual(master.rating_count,0)
        self.assertIsNone(master.rating_avg)
