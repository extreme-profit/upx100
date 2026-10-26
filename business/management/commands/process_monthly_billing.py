from django.core.management.base import BaseCommand

from business.billing import process_billing
from business.acquiring import sync_payments
from business.reviews import process_review_invitations
from business.models import EmailNotification
from business.notifications import deliver_email


class Command(BaseCommand):
    help = 'Обработать счета, напоминания, приглашения к отзыву и повторить неотправленные письма'

    def handle(self, *args, **options):
        process_billing()
        sync_payments()
        process_review_invitations()
        pending = EmailNotification.objects.filter(sent_at__isnull=True, cancelled_at__isnull=True).values_list('pk', flat=True)
        sent = sum(deliver_email(pk) for pk in list(pending))
        self.stdout.write(f'Счета обработаны. Повторно отправлено писем: {sent}.')
