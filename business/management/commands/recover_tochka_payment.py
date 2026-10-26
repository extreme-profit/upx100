from django.core.management.base import BaseCommand, CommandError
from business.acquiring import recover_payment
from business.tochka import TochkaError


class Command(BaseCommand):
    help = 'Связать неопределённую попытку с operationId банка после ручной сверки по paymentLinkId'

    def add_arguments(self, parser):
        parser.add_argument('payment_id')
        parser.add_argument('operation_id')

    def handle(self, *args, **options):
        try:
            recover_payment(options['payment_id'], options['operation_id'])
        except (TochkaError, ValueError):
            raise CommandError('Банк не подтвердил соответствие операции. Данные не изменены.')
        self.stdout.write('Операция сверена через API банка.')
