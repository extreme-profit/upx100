from datetime import timedelta,time
from uuid import UUID, uuid4
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from business.models import Booking, Company, Service, ServiceTimeSlot


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BookingPublicUuidTests(TestCase):
    def setUp(self):
        self.company=Company.objects.create(owner=User.objects.create_user('uuid-owner@example.com',role='entrepreneur'),name='Компания',is_verified=True)
        self.service=Service.objects.create(company=self.company,name='Услуга',price=100)
        self.slot=ServiceTimeSlot.objects.create(service=self.service,date=timezone.localdate()+timedelta(days=1),start_time=time(12),end_time=time(13))

    def test_booking_redirect_contains_uuid_and_keeps_session_authorization(self):
        response=self.client.post(reverse('client:booking_create',args=[self.service.pk]),{
            'slot_id':self.slot.pk,'client_name':'Клиент','client_phone':'+79990000000','client_email':'uuid-client@example.com'})
        self.assertEqual(response.status_code,302)
        booking=Booking.objects.get()
        url=reverse('client:booking_success',args=[booking.public_id])
        self.assertEqual(response['Location'],url)
        self.assertEqual(UUID(url.rstrip('/').split('/')[-1]),booking.public_id)
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(Client().get(url).status_code,404)
        self.assertEqual(self.client.get(f'/client/booking/success/{booking.pk}/').status_code,404)
        self.assertEqual(self.client.get(reverse('client:booking_success',args=[uuid4()])).status_code,404)

    def test_known_uuid_of_someone_else_is_not_enough(self):
        own=Booking.objects.create(service=self.service,client_name='Первый',client_phone='1')
        other=Booking.objects.create(service=self.service,client_name='Другой',client_phone='2')
        session=self.client.session
        session['last_booking_id']=own.pk
        session.save()
        self.assertNotEqual(own.public_id,other.public_id)
        self.assertEqual(self.client.get(reverse('client:booking_success',args=[other.public_id])).status_code,404)
        self.assertEqual(self.client.get(reverse('client:booking_success',args=[own.public_id])).status_code,200)
