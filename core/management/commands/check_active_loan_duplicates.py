from django.core.management.base import BaseCommand
from django.db.models import Count

from ...models import LoanApplication, LoanStatus


class Command(BaseCommand):
    help = 'Report duplicate active loan applications before enforcing active-loan constraints'

    def handle(self, *args, **options):
        groups = LoanApplication.objects.filter(
            status__in=[LoanStatus.PENDING, LoanStatus.UNDER_REVIEW, LoanStatus.INFO_REQUIRED, LoanStatus.APPROVED]
        ).values('farmer_id', 'loan_product_id').annotate(total=Count('id')).filter(total__gt=1)
        groups = list(groups)
        if not groups:
            self.stdout.write(self.style.SUCCESS('No duplicate active loan applications found.'))
            return
        self.stdout.write(self.style.WARNING(f'Found {len(groups)} duplicate active application group(s):'))
        for group in groups:
            self.stdout.write(
                f"farmer={group['farmer_id']} loan_product={group['loan_product_id']} count={group['total']}"
            )
        self.stdout.write(self.style.ERROR('Resolve these groups before applying a restrictive uniqueness migration.'))
