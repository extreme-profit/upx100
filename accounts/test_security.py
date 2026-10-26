from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .models import User, SecurityEvent, FraudBlock
from .security import confirm_fraud, lift_fraud, record_event, remote_ip, find_block
from business.models import Company, Service
from business.forms import ServiceForm


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EntrepreneurAntiFraudTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('security-admin@example.com', 'password')
        self.owner = User.objects.create_user('security-owner@example.com', role='entrepreneur', phone='+7 (999) 123-45-67')
        self.company = Company.objects.create(owner=self.owner, name='Мастер', address='Адрес компании',
            phone='8 999 123 45 67', email=self.owner.email, is_verified=True)
        self.service = Service.objects.create(company=self.company, name='Ремонт', price=100, delivery_mode='visit')
        self.factory = RequestFactory()
        record_event(self.factory.get('/', REMOTE_ADDR='8.8.8.8'), self.owner, self.company, 'login')

    def block(self, **kwargs):
        return confirm_fraud(self.company, self.admin, 'Проверены обращения клиентов', 'Заявка №123, материалы проверки', **kwargs)

    def register(self, phone, email='repeat@example.com', ip='1.1.1.1', **headers):
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(reverse('accounts:register'), {
                'email':email, 'password':'valid-password-123', 'password_confirm':'valid-password-123',
                'company_name':'Новая компания', 'phone':phone, 'address':'Новый адрес',
            }, REMOTE_ADDR=ip, **headers)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=email)
        return client, user

    def test_same_phone_other_email_and_ip_is_blocked_and_only_admin_is_emailed(self):
        block = self.block()
        client, user = self.register('89991234567')
        self.assertTrue(user.company.fraud_blocked)
        event = user.security_events.get(action='registration_blocked')
        self.assertEqual(event.matched_block_id, block.pk)
        self.assertEqual(event.phone, '79991234567')
        self.assertEqual([m.to for m in mail.outbox], [[self.admin.email]])
        self.assertNotIn(user.email, [address for message in mail.outbox for address in message.to])
        self.assertEqual(client.get(reverse('business:service_create')).status_code, 403)
        self.assertEqual(client.post(reverse('business:service_create'), {'name':'Обход'}).status_code, 403)
        self.assertFalse(user.company.services.exists())
        self.assertEqual(client.get(reverse('business:company_profile')).status_code, 200)

    def test_phone_variants_and_ten_digit_mobile_match(self):
        self.block()
        for i, phone in enumerate(['+7 (999) 123-45-67','8 999 123 45 67','9991234567','0079991234567','＋７９９９１２３４５６７']):
            _, user = self.register(phone, f'variant-{i}@example.com')
            self.assertTrue(user.company.fraud_blocked)

    def test_local_russian_landline_matches_international_form(self):
        self.block(extra_phones=['+7 (495) 123-45-67'])
        _, user = self.register('4951234567')
        self.assertTrue(user.company.fraud_blocked)

    def test_same_public_ip_different_phone_can_be_blocked(self):
        self.block()
        _, user = self.register('+79998887766', ip='8.8.8.8')
        self.assertTrue(user.company.fraud_blocked)

    def test_ip_rule_can_be_disabled_and_unrelated_phone_is_not_blocked(self):
        self.block(block_ips=False)
        _, user = self.register('+79998887766', ip='8.8.8.8')
        self.assertFalse(user.company.fraud_blocked)
        self.assertFalse(user.security_events.filter(action='registration_blocked').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_untrusted_forwarded_ip_cannot_cause_block(self):
        self.block()
        _, user = self.register('+79998887766', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertFalse(user.company.fraud_blocked)

    @override_settings(ANTIFRAUD_TRUSTED_PROXY_CIDRS=['127.0.0.1/32'])
    def test_trusted_proxy_uses_rightmost_untrusted_address(self):
        request = self.factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='8.8.8.8, 1.1.1.1')
        self.assertEqual(remote_ip(request), '1.1.1.1')
        self.block()
        _, user = self.register('+79998887766', ip='127.0.0.1', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertTrue(user.company.fraud_blocked)

    def test_internal_ip_not_added_to_block_identifiers(self):
        record_event(self.factory.get('/', REMOTE_ADDR='127.0.0.1'), self.owner, self.company, 'login')
        record_event(self.factory.get('/', REMOTE_ADDR='10.0.0.1'), self.owner, self.company, 'login')
        block = self.block()
        self.assertFalse(block.identifiers.filter(value__in=['127.0.0.1','10.0.0.1']).exists())
        _, user = self.register('+79998887766', ip='127.0.0.1')
        self.assertFalse(user.company.fraud_blocked)

    def test_old_phone_is_preserved_and_existing_related_company_is_hidden(self):
        self.owner.phone = '+79990001122'
        self.owner.save(update_fields=['phone'])
        self.company.phone = '+79990001122'
        self.company.save(update_fields=['phone'])
        other = User.objects.create_user('old-phone@example.com', role='entrepreneur', phone='89991234567')
        linked = Company.objects.create(owner=other,name='Связанная',is_verified=True)
        linked_service = Service.objects.create(company=linked,name='Другая услуга',price=200)
        self.block()
        linked.refresh_from_db()
        self.assertTrue(linked.fraud_blocked)
        self.assertFalse(Service.objects.visible().filter(pk=linked_service.pk).exists())
        _, repeat = self.register('89991234567')
        self.assertTrue(repeat.company.fraud_blocked)

    def test_services_company_pages_booking_and_form_are_restricted(self):
        self.block()
        self.assertFalse(Service.objects.visible().filter(pk=self.service.pk).exists())
        for name,args in [('client:service_detail',[self.service.pk]),('client:company_detail',[self.company.pk]),('business:company_public_profile',[self.company.pk])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,404)
        self.assertEqual(self.client.post(reverse('client:booking_create',args=[self.service.pk]),{}).status_code,404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('business:service_edit',args=[self.service.pk]),{}).status_code,403)
        form = ServiceForm(data={},company=self.company)
        self.assertFalse(form.is_valid())
        self.assertIn('Публикация',str(form.non_field_errors()))
        self.company.refresh_from_db()
        self.assertEqual(self.service.status,'inactive')

    def test_manual_block_does_not_create_permanent_phone_ban(self):
        self.company.is_blocked = True
        self.company.save(update_fields=['is_blocked'])
        _, user = self.register('89991234567')
        self.assertFalse(user.company.fraud_blocked)
        self.assertEqual(FraudBlock.objects.count(),0)

    def test_manual_unblock_or_verification_cannot_override_fraud(self):
        self.block()
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:user_toggle_services',args=[self.owner.pk]))
        self.company.refresh_from_db()
        self.assertTrue(self.company.fraud_blocked)
        self.client.post(reverse('dashboard:user_verify',args=[self.owner.pk]))
        self.assertFalse(Service.objects.visible().filter(pk=self.service.pk).exists())

    def test_lift_requires_reason_releases_related_users_and_preserves_manual_block(self):
        block = self.block()
        _, repeat = self.register('89991234567')
        self.company.is_blocked = True
        self.company.save(update_fields=['is_blocked'])
        with self.assertRaises(ValidationError):
            lift_fraud(block.pk,self.admin,'')
        lift_fraud(block.pk,self.admin,'Ошибка в материалах, решение пересмотрено')
        self.company.refresh_from_db()
        repeat.company.refresh_from_db()
        self.assertFalse(self.company.fraud_blocked)
        self.assertFalse(repeat.company.fraud_blocked)
        self.assertTrue(self.company.is_blocked)
        block.refresh_from_db()
        self.assertIsNotNone(block.lifted_at)
        self.assertEqual(block.lifted_by,self.admin)
        _, allowed = self.register('89991234567','after-lift@example.com')
        self.assertFalse(allowed.company.fraud_blocked)

    def test_other_active_block_is_preserved_when_one_is_lifted(self):
        block = self.block()
        other = User.objects.create_user('second-case@example.com',role='entrepreneur',phone='89991234567')
        company = Company.objects.create(owner=other,name='Вторая',phone=other.phone)
        confirm_fraud(company,self.admin,'Другой подтверждённый эпизод')
        lift_fraud(block.pk,self.admin,'Пересмотр первого эпизода')
        self.company.refresh_from_db()
        self.assertTrue(self.company.fraud_blocked)

    def test_registry_and_export_are_private_and_snapshot_is_immutable(self):
        block = self.block()
        self.company.name = 'Новое название'
        self.company.save(update_fields=['name'])
        for user in [None,self.owner]:
            client = Client()
            if user:
                client.force_login(user)
            for name,args in [('dashboard:blocked_users',[]),('dashboard:export_fraud',[block.pk]),('dashboard:confirm_user_fraud',[self.owner.pk])]:
                self.assertEqual(client.get(reverse(name,args=args)).status_code,302)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard:export_fraud',args=[block.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['snapshot']['company']['name'],'Мастер')
        self.assertEqual(response.json()['snapshot']['owner']['phone'],'+7 (999) 123-45-67')
        self.assertEqual(response.json()['snapshot']['employees'],[])
        self.assertIn('attachment',response['Content-Disposition'])
        self.assertIn('no-store',response['Cache-Control'])
        self.assertContains(self.client.get(reverse('dashboard:blocked_users')), 'security-owner@example.com')
        self.assertContains(self.client.get(reverse('dashboard:blocked_users'),{'q':'8.8.8.8'}), 'IP: 8.8.8.8')
        with self.assertRaises(ProtectedError):
            self.company.delete()

    def test_decision_needs_admin_and_explicit_confirmation_and_lift_is_post_only(self):
        with self.assertRaises(PermissionDenied):
            confirm_fraud(self.company,self.owner,'Не администратор')
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:confirm_user_fraud',args=[self.owner.pk]), {'reason':'Только жалоба'})
        self.assertFalse(FraudBlock.objects.exists())
        response = self.client.post(reverse('dashboard:confirm_user_fraud',args=[self.owner.pk]), {
            'reason':'Проверены доказательства','confirmed':'on','block_ips':'on'})
        self.assertEqual(response.status_code,302)
        block = FraudBlock.objects.get()
        self.assertEqual(self.client.get(reverse('dashboard:lift_user_fraud',args=[block.pk])).status_code,405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('dashboard:lift_user_fraud',args=[block.pk]),{'reason':'Проверка'}).status_code,403)

    def test_phone_required_on_registration(self):
        response = self.client.post(reverse('accounts:register'),{
            'email':'missing-phone@example.com','company_name':'Компания','password':'valid-pass','password_confirm':'valid-pass'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(User.objects.filter(email='missing-phone@example.com').exists())
