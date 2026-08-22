from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Repayment, RepaymentStatus
from ...services.notification_service import send_event_sms
from ...services.repayment_service import refresh_repayment_statuses


class Command(BaseCommand):
    help = 'Refresh repayment statuses and send idempotent due/overdue reminders'

    def handle(self, *args, **options):
        today = timezone.localdate()
        refresh_repayment_statuses(today)
        rows = Repayment.objects.select_related('loan__application__farmer').filter(
            status__in=[RepaymentStatus.DUE, RepaymentStatus.OVERDUE]
        )
        sent = 0
        for repayment in rows:
            farmer = repayment.loan.application.farmer
            event = 'overdue' if repayment.status == RepaymentStatus.OVERDUE else 'due'
            key = f'repayment-{event}-{repayment.id}-{repayment.due_date.isoformat()}'
            message = (
                f'Lunyili AgroSmart: Malipo ya awamu {repayment.installment_number} '
                f'ya TSh {int(repayment.remaining_balance):,} '
                f"{'yamechelewa' if event == 'overdue' else 'yanatakiwa'} "
                f'kabla ya {repayment.due_date.strftime("%d/%m/%Y")}. '
                'Piga *566# kwa maelekezo.'
            )
            send_event_sms(key, farmer.phone_number, message)
            sent += 1
        self.stdout.write(self.style.SUCCESS(f'Processed {sent} repayment reminders.'))
