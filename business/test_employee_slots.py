from datetime import timedelta, time
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from .models import Booking, Company, Employee, Service, ServiceTimeSlot


class EmployeeScheduleAccessTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('schedule-owner@example.com',role='entrepreneur')
        self.company=Company.objects.create(owner=self.owner,name='Компания',is_verified=True)
        self.user=User.objects.create_user('schedule-employee@example.com',role='employee')
        self.employee=Employee.objects.create(company=self.company,user=self.user)
        self.colleague=Employee.objects.create(company=self.company,user=User.objects.create_user('schedule-colleague@example.com',role='employee'))
        self.service=Service.objects.create(company=self.company,name='Услуга',price=100,duration=30)
        self.service.employees.add(self.employee,self.colleague)
        self.unassigned=Service.objects.create(company=self.company,name='Не назначена',price=100,duration=30)
        self.unassigned.employees.add(self.colleague)
        other=Company.objects.create(owner=User.objects.create_user('schedule-other@example.com',role='entrepreneur'),name='Другая')
        self.foreign=Service.objects.create(company=other,name='Чужая',price=100,duration=30)
        self.day=timezone.localdate()+timedelta(days=1)
        self.week_offset=(self.day-(timezone.localdate()-timedelta(days=timezone.localdate().weekday()))).days//7
        self.client.force_login(self.user)

    def generate_data(self,**extra):
        return {'start_date':self.day.isoformat(),'end_date':self.day.isoformat(),
            'schedule_type':'all_week','duration':30,'start_time':'09:00','end_time':'10:00',**extra}

    def bulk(self,**extra):
        return self.client.post(reverse('business:slot_bulk_update',args=[self.service.pk]),{
            'schedule_type':'all_week','start_hour':9,'end_hour':10,'action':'set_free',
            'period_start':self.day.isoformat(),'period_end':self.day.isoformat(),**extra}, content_type='application/json')

    def test_employee_generation_works_and_defaults_to_own_schedule(self):
        url=reverse('business:slot_generate',args=[self.service.pk])
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(list(response.context['form'].fields['employees'].queryset),[self.employee])
        self.assertEqual(self.client.post(url,self.generate_data()).status_code,302)
        self.assertEqual(self.service.time_slots.count(),2)
        self.assertEqual(set(self.service.time_slots.values_list('employee_id',flat=True)),{self.employee.pk})
        self.client.post(url,self.generate_data())
        self.assertEqual(self.service.time_slots.count(),2)

    def test_generator_rejects_another_employee(self):
        response=self.client.post(reverse('business:slot_generate',args=[self.service.pk]),self.generate_data(employees=[self.colleague.pk]))
        self.assertEqual(response.status_code,200)
        self.assertIn('employees',response.context['form'].errors)
        self.assertFalse(self.service.time_slots.exists())

    def test_employee_cannot_access_unassigned_or_foreign_services_by_number(self):
        for service in [self.unassigned,self.foreign]:
            for name in ['service_detail','slot_manage','slot_generate','slot_get_grid']:
                with self.subTest(service=service.pk,page=name):
                    self.assertEqual(self.client.get(reverse('business:'+name,args=[service.pk])).status_code,404)
            self.assertEqual(self.client.post(reverse('business:slot_generate',args=[service.pk]),self.generate_data()).status_code,404)

    def test_owner_can_manage_all_assigned_employees_but_not_foreign_company(self):
        self.client.force_login(self.owner)
        foreign_employee=Employee.objects.create(company=self.foreign.company,
            user=User.objects.create_user('foreign-schedule-employee@example.com',role='employee'))
        self.service.employees.add(foreign_employee)
        self.assertEqual(self.client.post(reverse('business:slot_generate',args=[self.service.pk]),self.generate_data()).status_code,302)
        self.assertEqual(self.service.time_slots.count(),4)
        self.assertEqual(self.client.get(reverse('business:service_detail',args=[self.foreign.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('business:slot_generate',args=[self.foreign.pk])).status_code,404)

    def test_grid_and_bulk_requests_cannot_target_colleagues(self):
        own=ServiceTimeSlot.objects.create(service=self.service,employee=self.employee,date=self.day,start_time=time(9),end_time=time(9,30))
        colleague=ServiceTimeSlot.objects.create(service=self.service,employee=self.colleague,date=self.day,start_time=time(9,30),end_time=time(10))
        response=self.client.get(reverse('business:slot_get_grid',args=[self.service.pk]),{'week_offset':self.week_offset})
        self.assertEqual(response.status_code,200)
        self.assertEqual({item['slot_id'] for item in response.json()['grid'].values()},{own.pk})
        self.assertEqual(self.client.get(reverse('business:slot_get_grid',args=[self.service.pk]),{'employee':self.colleague.pk}).status_code,404)
        self.assertEqual(self.bulk(employees=[self.colleague.pk]).status_code,404)
        self.assertEqual(self.client.post(reverse('business:slot_update_grid',args=[self.service.pk]),{
            'weekday':self.day.weekday(),'hour':9,'employee':self.colleague.pk,'action':'set_busy'},content_type='application/json').status_code,404)
        self.assertEqual(self.bulk().status_code,200)
        colleague.refresh_from_db()
        self.assertFalse(colleague.is_booked)
        self.assertEqual(self.service.time_slots.filter(employee=self.colleague).count(),1)

    def test_inactive_employee_cannot_generate_or_manage_slots(self):
        self.employee.is_active=False
        self.employee.save(update_fields=['is_active'])
        for name in ['service_detail','slot_manage','slot_generate','slot_get_grid']:
            self.assertEqual(self.client.get(reverse('business:'+name,args=[self.service.pk])).status_code,404)
        self.assertEqual(self.bulk().status_code,404)

    def test_bookings_are_not_detached_by_grid_bulk_or_toggle(self):
        booking=Booking.objects.create(service=self.service,employee=self.employee,client_name='Клиент',client_phone='123')
        slot=ServiceTimeSlot.objects.create(service=self.service,employee=self.employee,booking=booking,is_booked=True,
            date=self.day,start_time=time(9),end_time=time(9,30))
        update=self.client.post(reverse('business:slot_update_grid',args=[self.service.pk]),{
            'weekday':self.day.weekday(),'hour':9,'employee':self.employee.pk,'action':'set_free',
            'week_offset':self.week_offset},content_type='application/json')
        self.assertEqual(update.status_code,409)
        self.assertEqual(self.bulk(action='set_free',set_others_busy=True).status_code,200)
        self.assertEqual(self.client.post(reverse('business:slot_toggle',args=[slot.pk])).status_code,409)
        slot.refresh_from_db()
        self.assertEqual(slot.booking_id,booking.pk)
        self.assertTrue(slot.is_booked)

    def test_single_slot_change_cannot_touch_colleague_and_is_post_only(self):
        slot=ServiceTimeSlot.objects.create(service=self.service,employee=self.colleague,date=self.day,start_time=time(9),end_time=time(10))
        url=reverse('business:slot_toggle',args=[slot.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertEqual(self.client.post(url).status_code,404)
        slot.refresh_from_db()
        self.assertFalse(slot.is_booked)
