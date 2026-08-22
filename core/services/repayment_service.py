# core/services/repayment_service.py

from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import uuid
import re
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging

from ..models import (
    Loan,
    LoanApplication,
    LoanStatus,
    PaymentTransaction,
    PaymentTransactionStatus,
    Repayment,
    RepaymentStatus,
)

logger = logging.getLogger(__name__)

MONEY = Decimal('0.01')


def _frequency_days(frequency):
    return {
        'WEEKLY': 7,
        'BIWEEKLY': 14,
        'MONTHLY': 30,
        'QUARTERLY': 90,
    }.get((frequency or 'MONTHLY').upper(), 30)


def _installment_count(product):
    days = _frequency_days(product.repayment_frequency)
    total_days = max(product.duration_months * 30, days)
    return max(1, (total_days + days - 1) // days)


def generate_repayment_schedule(loan):
    """Create the schedule once using the selected product's approved terms."""
    with transaction.atomic():
        locked_loan = Loan.objects.select_for_update().select_related(
            'application__loan_product'
        ).get(pk=loan.pk)
        
        if locked_loan.repayments.exists():
            return list(locked_loan.repayments.order_by('installment_number'))

        product = locked_loan.application.loan_product
        count = _installment_count(product)
        
        total_interest = (locked_loan.principal_amount * product.interest_rate / Decimal('100')).quantize(MONEY, rounding=ROUND_HALF_UP)
        locked_loan.interest_amount = total_interest
        locked_loan.outstanding_balance = locked_loan.principal_amount + total_interest
        locked_loan.maturity_date = (
            (locked_loan.disbursed_at or timezone.now()).date()
            + timedelta(days=_frequency_days(product.repayment_frequency) * count)
        )
        locked_loan.save(update_fields=['interest_amount', 'outstanding_balance', 'maturity_date', 'updated_at'])

        principal_base = (locked_loan.principal_amount / count).quantize(MONEY, rounding=ROUND_HALF_UP)
        interest_base = (total_interest / count).quantize(MONEY, rounding=ROUND_HALF_UP)
        start_date = (locked_loan.disbursed_at or timezone.now()).date()
        grace = product.grace_period_days or 0
        frequency_days = _frequency_days(product.repayment_frequency)
        
        rows = []
        for number in range(1, count + 1):
            principal = principal_base if number < count else locked_loan.principal_amount - principal_base * (count - 1)
            interest = interest_base if number < count else total_interest - interest_base * (count - 1)
            due_date = start_date + timedelta(days=grace + frequency_days * number)
            status = RepaymentStatus.DUE if due_date <= timezone.localdate() else RepaymentStatus.UPCOMING
            rows.append(Repayment(
                loan=locked_loan,
                installment_number=number,
                due_date=due_date,
                principal_due=principal,
                interest_due=interest,
                total_due=principal + interest,
                status=status,
            ))
        Repayment.objects.bulk_create(rows)
        return rows


def initiate_repayment_via_ussd(loan, amount=None):
    """
    Initiate repayment via USSD push.
    Sends a USSD push notification to the farmer to confirm payment.
    """
    # Find the next due repayment
    repayment = loan.repayments.filter(
        status__in=[RepaymentStatus.DUE, RepaymentStatus.OVERDUE, RepaymentStatus.PARTIALLY_PAID]
    ).order_by('installment_number').first()
    
    if not repayment:
        return None, "Hakuna malipo yanayodaiwa kwa sasa."
    
    # If amount not specified, use the full remaining balance
    if amount is None or amount <= 0:
        amount = repayment.remaining_balance
    
    # Create payment transaction
    reference = f'PAY-{uuid.uuid4().hex[:20].upper()}'
    
    payment = PaymentTransaction.objects.create(
        loan=loan,
        repayment=repayment,
        provider='MANUAL_INSTRUCTION',
        provider_reference=reference,
        amount=amount,
        status=PaymentTransactionStatus.INITIATED,
    )
    
    # Send USSD push via ClickPesa
    try:
        from .clickpesa_service import get_clickpesa_provider
        provider = get_clickpesa_provider()
        
        result = provider.request_payment(
            amount=amount,
            payer=loan.application.farmer.phone_number,
            reference=reference,
            metadata={
                'loan_id': str(loan.id),
                'repayment_id': str(repayment.id),
                'installment_number': repayment.installment_number,
                'description': f'Malipo ya mkopo - Kipindi {repayment.installment_number}',
            }
        )
        
        if result.get('status') == 'success':
            payment.status = PaymentTransactionStatus.PENDING
            payment.provider = 'CLICKPESA'
            payment.provider_payload = result.get('data', {})
            payment.save(update_fields=['status', 'provider', 'provider_payload', 'updated_at'])
            
            # Send SMS with fallback link
            _send_repayment_sms(
                loan.application.farmer.phone_number,
                amount,
                repayment,
                result.get('checkout_url')
            )
            
            return payment, "Ombi la malipo limetumwa. Utapokea ujumbe wa kuthibitisha."
        else:
            payment.status = PaymentTransactionStatus.FAILED
            payment.failure_reason = result.get('reason', 'Unknown error')[:255]
            payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
            return payment, f"Samahani, malipo hayakufanikiwa: {result.get('reason', '')}"
            
    except Exception as e:
        logger.exception(f"Repayment initiation error: {str(e)}")
        payment.status = PaymentTransactionStatus.FAILED
        payment.failure_reason = str(e)[:255]
        payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return payment, f"Samahani, kuna tatizo. Jaribu tena baadaye."


def _send_repayment_sms(phone_number, amount, repayment, checkout_url=None):
    """Send repayment notification with USSD push instructions and fallback link"""
    try:
        from .notification_service import send_event_sms
        
        message = (
            f"Lunyili AgroSmart\n"
            f"Malipo ya mkopo: TSh {int(amount):,}\n"
            f"Kipindi #{repayment.installment_number}\n"
        )
        
        if checkout_url:
            message += f"\nIkiwa USSD haifanyi kazi, fungua: {checkout_url}"
        else:
            message += "\nUtapokea mwaliko wa malipo kwenye simu yako."
        
        import uuid
        event_key = f"repayment-{uuid.uuid4().hex[:12]}"
        send_event_sms(event_key, phone_number, message)
        
    except Exception as e:
        logger.error(f"Failed to send repayment SMS: {str(e)}")


def initiate_payment(loan, amount, provider='MANUAL_INSTRUCTION'):
    """
    Legacy function - used by USSD engine.
    Now uses initiate_repayment_via_ussd internally.
    """
    if provider == 'CLICKPESA':
        return initiate_repayment_via_ussd(loan, amount)
    
    # Fallback to manual payment
    reference = f'PAY-{uuid.uuid4().hex[:20].upper()}'
    repayment = loan.repayments.filter(
        status__in=[RepaymentStatus.DUE, RepaymentStatus.OVERDUE, RepaymentStatus.PARTIALLY_PAID]
    ).order_by('installment_number').first()
    
    return PaymentTransaction.objects.create(
        loan=loan,
        repayment=repayment,
        provider=provider,
        provider_reference=reference,
        amount=amount,
        status=PaymentTransactionStatus.INITIATED,
    )


def confirm_payment(provider_reference, payload=None):
    """Apply a provider confirmation exactly once and update balances atomically."""
    payload = payload or {}
    
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().select_related('loan').get(
            provider_reference=provider_reference
        )
        
        if payment.status == PaymentTransactionStatus.CONFIRMED:
            return payment
        if payment.status == PaymentTransactionStatus.FAILED:
            return payment

        loan = Loan.objects.select_for_update().get(pk=payment.loan_id)
        repayments = list(Repayment.objects.select_for_update().filter(
            loan=loan,
            status__in=[RepaymentStatus.UPCOMING, RepaymentStatus.DUE, RepaymentStatus.OVERDUE, RepaymentStatus.PARTIALLY_PAID],
        ).order_by('installment_number'))
        
        if not repayments:
            payment.status = PaymentTransactionStatus.FAILED
            payment.failure_reason = 'No outstanding repayment'
            payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
            return payment

        remaining_payment = payment.amount
        applied_total = Decimal('0')
        first_repayment = repayments[0]
        
        for repayment in repayments:
            if remaining_payment <= 0:
                break
            applied = min(remaining_payment, repayment.remaining_balance)
            repayment.paid_amount += applied
            repayment.status = RepaymentStatus.PAID if repayment.remaining_balance == 0 else RepaymentStatus.PARTIALLY_PAID
            repayment.paid_at = timezone.now() if repayment.status == RepaymentStatus.PAID else None
            repayment.save(update_fields=['paid_amount', 'status', 'paid_at', 'updated_at'])
            remaining_payment -= applied
            applied_total += applied

        loan.outstanding_balance = max(loan.outstanding_balance - applied_total, Decimal('0'))
        
        if loan.outstanding_balance == 0:
            loan.status = LoanStatus.FULLY_REPAID
            loan.application.status = LoanStatus.FULLY_REPAID
            loan.application.save(update_fields=['status', 'updated_at'])
        elif any(row.status == RepaymentStatus.OVERDUE for row in repayments):
            loan.status = LoanStatus.OVERDUE
            loan.application.status = LoanStatus.OVERDUE
            loan.application.save(update_fields=['status', 'updated_at'])
        else:
            loan.status = LoanStatus.PARTIALLY_REPAID
            loan.application.status = LoanStatus.PARTIALLY_REPAID
            loan.application.save(update_fields=['status', 'updated_at'])
        
        loan.save(update_fields=['outstanding_balance', 'status', 'updated_at'])

        payment.repayment = first_repayment
        payment.status = PaymentTransactionStatus.CONFIRMED
        payment.confirmed_at = timezone.now()
        payment.provider_payload = payload
        payment.save(update_fields=['repayment', 'status', 'confirmed_at', 'provider_payload', 'updated_at'])
        
        return payment


def fail_payment(provider_reference, reason='', payload=None):
    """Persist a provider failure without changing any loan or repayment balance."""
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().get(provider_reference=provider_reference)
        if payment.status != PaymentTransactionStatus.CONFIRMED:
            payment.status = PaymentTransactionStatus.FAILED
            payment.failure_reason = reason[:255]
            payment.provider_payload = payload or {}
            payment.save(update_fields=['status', 'failure_reason', 'provider_payload', 'updated_at'])
        return payment


def refresh_repayment_statuses(today=None):
    """Update repayment statuses based on due dates"""
    today = today or timezone.localdate()
    
    Repayment.objects.filter(
        status=RepaymentStatus.UPCOMING,
        due_date__lte=today,
        paid_amount=0,
    ).update(status=RepaymentStatus.DUE)
    
    Repayment.objects.filter(
        status__in=[RepaymentStatus.DUE, RepaymentStatus.PARTIALLY_PAID],
        due_date__lt=today,
    ).exclude(status=RepaymentStatus.PAID).update(status=RepaymentStatus.OVERDUE)