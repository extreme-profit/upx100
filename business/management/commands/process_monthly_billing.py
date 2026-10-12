from django.core.management.base import BaseCommand

from business.billing import process_billing
from business.models import EmailNotification
from business.notifications import deliver_email


class Command(BaseCommand):
    help = 'Создать ежемесячные счета, отправить напоминания и повторить неотправленные письма'

    def handle(self, *args, **options):
        process_billing()
        pending = EmailNotification.objects.filter(sent_at__isnull=True).values_list('pk', flat=True)
        sent = sum(deliver_email(pk) for pk in list(pending))
        self.stdout.write(f'Счета обработаны. Повторно отправлено писем: {sent}.')
