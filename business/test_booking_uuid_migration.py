from uuid import UUID
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BookingUuidMigrationTests(TransactionTestCase):
    def test_existing_bookings_receive_distinct_uuids_without_changing_primary_keys(self):
        executor=MigrationExecutor(connection)
        current=executor.loader.graph.leaf_nodes()
        previous=[('business','0017_company_fraud_blocked'),('accounts','0003_fraudblock_fraudidentifier_securityevent_and_more')]
        executor.migrate(previous)
        try:
            apps=executor.loader.project_state(previous).apps
            User=apps.get_model('accounts','User')
            Company=apps.get_model('business','Company')
            Service=apps.get_model('business','Service')
            Booking=apps.get_model('business','Booking')
            owner=User.objects.create(email='migration-uuid@example.com',role='entrepreneur')
            company=Company.objects.create(owner=owner,name='Компания')
            service=Service.objects.create(company=company,name='Услуга',price=100)
            ids=[Booking.objects.create(service=service,client_name=name,client_phone='123').pk for name in ['Первый','Второй']]
            executor=MigrationExecutor(connection)
            executor.migrate(current)
            Booking=executor.loader.project_state(current).apps.get_model('business','Booking')
            rows=list(Booking.objects.filter(pk__in=ids).order_by('pk'))
            self.assertEqual([row.pk for row in rows],ids)
            self.assertEqual(len({row.public_id for row in rows}),2)
            self.assertTrue(all(isinstance(row.public_id,UUID) for row in rows))
        finally:
            MigrationExecutor(connection).migrate(current)
