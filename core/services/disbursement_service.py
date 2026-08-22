# core/services/disbursement_service.py

import re
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging

from ..models import (
    Loan, LoanApplication, LoanDisbursement, LoanStatus, 
    OrderStatus, SMSMessage
)

logger = logging.getLogger(__name__)


class PaymentProvider:
    name = 'UNCONFIGURED'

    def disburse(self, *, amount: Decimal, recipient: str, idempotency_key: str, metadata: dict):
        raise NotImplementedError


class UnconfiguredPaymentProvider(PaymentProvider):
    name = 'UNCONFIGURED'

    def disburse(self, **kwargs):
        return {
            'status': 'pending',
            'reference': '',
            'reason': 'No authorised payment provider configured',
        }


def get_payment_provider():
    """Get configured payment provider"""
    provider_type = getattr(settings, 'PAYMENT_PROVIDER', 'unconfigured')
    
    if provider_type == 'clickpesa':
        from .clickpesa_service import get_clickpesa_provider
        return get_clickpesa_provider()
    
    return UnconfiguredPaymentProvider()


def _recipient_for(application):
    """
    Determine recipient for disbursement.
    
    INPUT LOAN → Supplier
    CASH/PRODUCTION LOAN → Farmer
    """
    if application.loan_product.loan_type == 'INPUT':
        # Input loan: pay supplier directly
        if not application.order:
            raise ValueError('Input loan requires an order')
        
        supplier = application.order.supplier
        if not supplier or not supplier.phone:
            raise ValueError('Supplier has no payment recipient')
        
        # Normalize phone number
        phone = re.sub(r'[^0-9]', '', supplier.phone)
        if phone.startswith('0'):
            phone = '255' + phone[1:]
        elif not phone.startswith('255'):
            phone = '255' + phone
        
        return phone
    
    # Cash/Production loan: pay farmer
    farmer = application.farmer
    if not getattr(farmer, 'payout_account_verified', False):
        raise ValueError('Farmer has no verified payout account')
    
    # Use phone number for mobile money
    phone = re.sub(r'[^0-9]', '', farmer.phone_number)
    if phone.startswith('0'):
        phone = '255' + phone[1:]
    elif not phone.startswith('255'):
        phone = '255' + phone
    
    return phone


def _get_recipient_type(application):
    """Get recipient type for metadata"""
    if application.loan_product.loan_type == 'INPUT':
        return 'supplier'
    return 'farmer'


def _send_sms(phone_number: str, message: str):
    """Send SMS notification"""
    try:
        from .notification_service import send_event_sms
        import uuid
        event_key = f"disbursement-{uuid.uuid4().hex[:12]}"
        send_event_sms(event_key, phone_number, message)
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")


def request_disbursement(application):
    """
    Request disbursement after farmer acceptance.
    
    Flow:
    1. Validate status (must be FARMER_ACCEPTED)
    2. Determine recipient (Supplier for INPUT, Farmer for CASH)
    3. Create Loan and LoanDisbursement records
    4. Call payment provider
    5. Handle success/failure
    """
    with transaction.atomic():
        locked = LoanApplication.objects.select_for_update().select_related(
            'farmer', 'loan_product', 'order__supplier'
        ).get(pk=application.pk)
        
        if locked.status != LoanStatus.FARMER_ACCEPTED:
            raise ValueError('Loan must be accepted before disbursement')
        
        # Check for existing disbursement (idempotency)
        existing = LoanDisbursement.objects.filter(application=locked).first()
        if existing:
            if existing.status == LoanDisbursement.Status.SUCCESS:
                return existing
            if existing.status == LoanDisbursement.Status.PENDING:
                # Return pending, don't retry
                return existing
        
        recipient = _recipient_for(locked)
        recipient_type = _get_recipient_type(locked)
        
        # Update application status
        locked.status = LoanStatus.DISBURSEMENT_PENDING
        locked.save(update_fields=['status', 'updated_at'])
        
        key = f'loan-disbursement-{locked.pk}'
        
        # Create loan record
        loan, _ = Loan.objects.get_or_create(
            application=locked,
            defaults={
                'principal_amount': locked.amount,
                'outstanding_balance': locked.amount,
                'status': LoanStatus.DISBURSEMENT_PENDING,
            },
        )
        
        # Create disbursement record
        disbursement, created = LoanDisbursement.objects.get_or_create(
            application=locked,
            defaults={
                'loan': loan,
                'provider': get_payment_provider().name,
                'idempotency_key': key,
                'amount': locked.amount,
                'recipient': recipient,
            },
        )
        
        if not created:
            return disbursement
        
        provider = get_payment_provider()
        
        # Execute disbursement
        result = provider.disburse(
            amount=locked.amount,
            recipient=recipient,
            idempotency_key=key,
            metadata={
                'application_id': str(locked.pk),
                'loan_type': locked.loan_product.loan_type,
                'farmer_id': str(locked.farmer.id),
                'recipient_type': recipient_type,
            },
        )
        
        # Update disbursement record
        status_map = {
            'success': LoanDisbursement.Status.SUCCESS,
            'failed': LoanDisbursement.Status.FAILED,
            'reversed': LoanDisbursement.Status.REVERSED,
        }
        
        disbursement.status = status_map.get(result.get('status'), LoanDisbursement.Status.PENDING)
        disbursement.provider_reference = result.get('reference', '')
        disbursement.failure_reason = result.get('reason', '')[:255]
        disbursement.provider_result = result
        disbursement.completed_at = timezone.now() if disbursement.status == LoanDisbursement.Status.SUCCESS else None
        disbursement.save(update_fields=[
            'status', 'provider_reference', 'failure_reason', 
            'provider_result', 'completed_at', 'updated_at'
        ])
        
        if disbursement.status == LoanDisbursement.Status.SUCCESS:
            _mark_disbursed(locked, loan)
        else:
            # Send notification about pending/failed disbursement
            _send_disbursement_notification(locked, disbursement)
        
        return disbursement


def _mark_disbursed(application, loan):
    """Mark loan as disbursed and create repayment schedule"""
    from .repayment_service import generate_repayment_schedule
    
    now = timezone.now()
    
    # Update application
    application.status = LoanStatus.DISBURSED
    application.save(update_fields=['status', 'updated_at'])
    
    # Update loan
    loan.status = LoanStatus.ACTIVE
    loan.disbursed_at = now
    loan.save(update_fields=['status', 'disbursed_at', 'updated_at'])
    
    # Generate repayment schedule
    generate_repayment_schedule(loan)
    
    # Update order if input loan
    if application.order_id:
        application.order.status = OrderStatus.SUPPLIER_PAID
        application.order.payment_status = 'COMPLETED'
        application.order.save(update_fields=['status', 'payment_status', 'updated_at'])
    
    # Send success notifications
    _send_disbursement_notification(application, None, success=True)


def _send_disbursement_notification(application, disbursement=None, success=False):
    """Send SMS notifications for disbursement"""
    farmer = application.farmer
    
    if success:
        # Success notification
        farmer_msg = (
            f"Lunyili AgroSmart\n"
            f"Mkopo wako wa TSh {int(application.amount):,} umetolewa!\n"
            f"Bidhaa: {application.loan_product.name}\n"
            f"Piga *566# kuona ratiba ya marejesho."
        )
        _send_sms(farmer.phone_number, farmer_msg)
        
        # For input loans, also notify supplier
        if application.loan_product.loan_type == 'INPUT' and application.order:
            supplier = application.order.supplier
            if supplier and supplier.phone:
                supplier_msg = (
                    f"Lunyili AgroSmart\n"
                    f"Malipo ya mkopo yamekamilika!\n"
                    f"Oda #{application.order.reference}\n"
                    f"Mkulima: {farmer.full_name}\n"
                    f"Kiasi: TSh {int(application.amount):,}\n"
                    f"Tafadhali anza usindikaji wa oda."
                )
                _send_sms(supplier.phone, supplier_msg)
    
    elif disbursement and disbursement.status == LoanDisbursement.Status.PENDING:
        # Pending notification
        msg = (
            f"Lunyili AgroSmart\n"
            f"Mkopo wako wa TSh {int(application.amount):,} umeidhinishwa.\n"
            f"Utoaji unaendelea. Utapata ujumbe wa uthibitisho hivi karibuni."
        )
        _send_sms(farmer.phone_number, msg)
    
    elif disbursement and disbursement.status == LoanDisbursement.Status.FAILED:
        # Failed notification
        msg = (
            f"Lunyili AgroSmart\n"
            f"Samahani, utoaji wa mkopo wako umeshindikana.\n"
            f"Tafadhali wasiliana na taasisi ya fedha.\n"
            f"Sababu: {disbursement.failure_reason[:100]}"
        )
        _send_sms(farmer.phone_number, msg)


def handle_disbursement_callback(provider_reference, status, payload=None):
    """
    Handle provider callback for disbursement confirmation.
    This is the only place where disbursement success is confirmed.
    """
    payload = payload or {}
    
    with transaction.atomic():
        record = LoanDisbursement.objects.select_for_update().select_related(
            'application', 'loan'
        ).get(provider_reference=provider_reference)
        
        # Already processed
        if record.status == LoanDisbursement.Status.SUCCESS:
            return record
        
        normalized = (status or '').lower()
        
        if normalized in {'failed', 'failure', 'cancelled', 'canceled'}:
            record.status = LoanDisbursement.Status.FAILED
            record.failure_reason = (payload.get('reason') or normalized)[:255]
            
        elif normalized in {'reversed', 'reversal'}:
            record.status = LoanDisbursement.Status.REVERSED
            
        elif normalized in {'success', 'successful', 'confirmed', 'completed'}:
            record.status = LoanDisbursement.Status.SUCCESS
            record.completed_at = timezone.now()
            _mark_disbursed(record.application, record.loan)
        else:
            return record
        
        record.provider_result = payload
        record.save(update_fields=[
            'status', 'failure_reason', 'completed_at', 
            'provider_result', 'updated_at'
        ])
        
        return record