from datetime import timedelta
from unittest.mock import patch
import uuid
from django.test import TestCase, Client, override_settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from .models import Company, Employee, Service, Booking, Review, EmailNotification
from .reviews import process_review_invitations, review_url


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReviewWorkflowTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('ratingowner@example.com', role='entrepreneur')
        company = Company.objects.create(owner=owner, name='Салон', is_verified=True)
        user = User.objects.create_user('ratingmaster@example.com', role='employee', first_name='Мастер')
        self.employee = Employee.objects.create(company=company, user=user)
        self.service = Service.objects.create(company=company, name='Стрижка', price=100)
        self.service.employees.add(self.employee)
        self.end = timezone.now()-timedelta(hours=25)
        self.booking = Booking.objects.create(service=self.service, employee=self.employee, client_name='Клиент', client_phone='123', client_email='ratingclient@example.com', status='confirmed', appointment_end_at=self.end, appointment_at=self.end-timedelta(hours=1))
        self.url = reverse('client:booking_review', args=[self.booking.review_token])

    def test_invitation_at_exactly_twenty_four_hours_and_only_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            process_review_invitations(self.end+timedelta(hours=24)-timedelta(seconds=1))
        self.assertEqual(EmailNotification.objects.count(),0)
        with self.captureOnCommitCallbacks(execute=True):
            process_review_invitations(self.end+timedelta(hours=24))
            process_review_invitations(self.end+timedelta(days=2))
        self.assertEqual(EmailNotification.objects.count(),1)
        self.assertEqual(len(mail.outbox),1)
        self.assertIn(review_url(self.booking), mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.booking.client_email])

    def test_token_only_validation_single_review_and_public_rating(self):
        self.assertEqual(self.client.get(reverse('client:booking_review', args=[uuid.uuid4()])).status_code,404)
        self.assertEqual(self.client.post(self.url, {'rating':6}).status_code,200)
        self.assertFalse(Review.objects.exists())
        response = self.client.post(self.url, {'rating':5,'comment':'<script>alert(1)</script>'})
        self.assertEqual(response.status_code,302)
        self.client.post(self.url, {'rating':1,'comment':'Changed'})
        review = Review.objects.get()
        self.assertEqual(review.rating,5)
        response = self.client.get(reverse('client:service_detail', args=[self.service.pk]))
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        other_booking = Booking.objects.create(service=self.service, employee=self.employee, client_name='Другой клиент', client_phone='456', status='completed', appointment_end_at=self.end)
        Review.objects.create(booking=other_booking, employee=self.employee, rating=3)
        response = self.client.get(reverse('client:service_detail', args=[self.service.pk]))
        employee = list(response.context['employees'])[0]
        self.assertEqual(employee.rating_avg,4)
        self.assertEqual(employee.rating_count,2)
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, {'rating':5}).status_code,403)

    def test_no_reviews_or_invitations_for_ineligible_booking(self):
        for status in ['pending','cancelled','client_cancelled']:
            self.booking.status = status
            self.booking.save()
            self.assertEqual(self.client.post(self.url, {'rating':5}).status_code,403)
            process_review_invitations()
        self.booking.status='confirmed'
        self.booking.appointment_end_at=timezone.now()+timedelta(hours=1)
        self.booking.save()
        self.assertEqual(self.client.get(self.url).status_code,403)
        process_review_invitations()
        self.booking.appointment_end_at=self.end
        self.booking.employee=None
        self.booking.save()
        self.assertEqual(self.client.get(self.url).status_code,403)
        process_review_invitations()
        self.assertFalse(Review.objects.exists())
        self.assertFalse(EmailNotification.objects.exists())

    def test_history_button_after_end_and_hidden_after_review(self):
        response=self.client.get(reverse('client:booking_history'))
        self.booking.visitor_id=response.wsgi_request.booking_visitor
        self.booking.save()
        url=reverse('client:booking_history')+'?tab=past'
        self.assertContains(self.client.get(url),'Оставить отзыв')
        self.client.post(self.url, {'rating':4,'comment':'Хорошо'})
        self.assertNotContains(self.client.get(url),'Оставить отзыв')
        self.assertContains(self.client.get(url),'Ваш отзыв: 4 из 5')
        process_review_invitations()
        self.assertFalse(EmailNotification.objects.exists())


    def test_booking_snapshots_master_and_end_across_midnight(self):
        from datetime import time
        from .models import ServiceTimeSlot
        from .booking_workflow import create_booking
        tomorrow = timezone.localdate()+timedelta(days=1)
        slot = ServiceTimeSlot.objects.create(service=self.service, employee=self.employee, date=tomorrow, start_time=time(23,30), end_time=time(1))
        booking = create_booking(self.service.pk, dict(slot_id=slot.pk, client_name='Ночь', client_phone='123', client_email='night@example.com', notes=''))
        self.assertEqual(booking.employee_id,self.employee.pk)
        local_end = timezone.localtime(booking.appointment_end_at, self.service.company.tzinfo)
        self.assertEqual(local_end.date(),tomorrow+timedelta(days=1))
        self.assertEqual(local_end.hour,1)
