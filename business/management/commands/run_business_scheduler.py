import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Планировщик счетов и повторной отправки писем (альтернатива cron)'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=60)

    def handle(self, *args, **options):
        interval = options['interval']
        if interval < 1:
            raise CommandError('Интервал должен быть положительным')
        while True:
            try:
                call_command('process_monthly_billing', stdout=self.stdout)
            except Exception as exc:
                self.stderr.write(f'Ошибка планировщика: {type(exc).__name__}. Повтор через {interval} секунд.')
            time.sleep(interval)
