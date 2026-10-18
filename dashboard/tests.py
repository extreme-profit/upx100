from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from business.models import Company, MonthlyInvoice


class DashboardBillingTests(TestCase):
    def test_statistics_and_debtors_include_only_pending_amounts(self):
        admin = User.objects.create_superuser('admin-stats@example.com', 'password')
        self.client.force_login(admin)
        owner = User.objects.create_user('active-stats@example.com', role='entrepreneur')
        company = Company.objects.create(owner=owner, name='Активная', is_verified=True)
        blocked_owner = User.objects.create_user('blocked-stats@example.com', role='entrepreneur')
        Company.objects.create(owner=blocked_owner, name='Скрытая', is_verified=True, is_blocked=True)
        for month, amount, status, due in [(1, 100, 'paid', date(2026, 2, 5)), (2, 200, 'pending', timezone.localdate() - timedelta(days=1)), (3, 300, 'pending', timezone.localdate() + timedelta(days=1))]:
            MonthlyInvoice.objects.create(company=company, period=date(2026, month, 1), amount=amount, status=status, due_date=due, gateway_reference=f'stats-{month}')
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['invoices_paid'], 1)
        self.assertEqual(response.context['invoices_total'], 3)
        self.assertEqual(response.context['invoices_paid_amount'], Decimal('100'))
        self.assertEqual(response.context['active_entrepreneurs'], 1)
        self.assertEqual(response.context['entrepreneurs_count'], 2)
        debtor, = response.context['debtors']
        self.assertEqual(debtor.unpaid_count, 2)
        self.assertEqual(debtor.unpaid_amount, Decimal('500'))
        self.assertEqual(debtor.overdue_count, 1)
        self.assertContains(response, owner.email)

    def test_dashboard_requires_admin(self):
        user = User.objects.create_user('nonadmin@example.com', role='entrepreneur')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('dashboard:home')).status_code, 302)
