from django.core.management.base import BaseCommand

from ...models import SMSMessage, SMSStatus
from ...services.notification_service import send_event_sms


class Command(BaseCommand):
    help = 'Retry failed idempotent business-event SMS notifications'

    def handle(self, *args, **options):
        messages = SMSMessage.objects.filter(
            status=SMSStatus.FAILED,
            event_key__isnull=False,
        ).order_by('created_at')
        count = 0
        for sms in messages:
            send_event_sms(sms.event_key, sms.recipient, sms.message)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Retried {count} notification(s).'))
