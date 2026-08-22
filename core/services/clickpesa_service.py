# core/services/clickpesa_service.py

import requests
import json
import uuid
import hmac
import hashlib
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class ClickPesaProvider:
    """ClickPesa payment provider implementation"""
    
    name = 'CLICKPESA'
    
    def __init__(self):
        self.client_id = settings.CLICKPESA_CLIENT_ID
        self.api_key = settings.CLICKPESA_API_KEY
        self.base_url = settings.CLICKPESA_BASE_URL
        self.dry_run = getattr(settings, 'CLICKPESA_DRY_RUN', True)
        self.webhook_secret = getattr(settings, 'CLICKPESA_WEBHOOK_SECRET', '')
        
    def _get_headers(self):
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'X-Client-ID': self.client_id,
        }
    
    def _is_success(self, response):
        """Check if response indicates success"""
        if self.dry_run:
            return True
        return response.status_code in [200, 201, 202, 204]
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to international format"""
        if not phone:
            return phone
        # Remove any non-digit characters
        cleaned = re.sub(r'[^0-9]', '', phone)
        # If starts with 0, replace with 255
        if cleaned.startswith('0'):
            cleaned = '255' + cleaned[1:]
        # If doesn't start with 255, add it
        elif not cleaned.startswith('255'):
            cleaned = '255' + cleaned
        return cleaned
    
    def disburse(self, *, amount: Decimal, recipient: str, idempotency_key: str, metadata: dict):
        """
        Disburse funds to recipient via ClickPesa.
        
        Args:
            amount: Amount to disburse
            recipient: Phone number (e.g., 255712345678)
            idempotency_key: Unique key to prevent duplicate
            metadata: Additional data (loan_id, application_id, etc.)
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] ClickPesa disbursement: {amount} to {recipient}")
            return {
                'status': 'success',
                'reference': f'DRY-{idempotency_key[:10]}',
                'reason': 'Dry run mode',
            }
        
        try:
            recipient = self._normalize_phone(recipient)
            
            payload = {
                'amount': str(amount),
                'recipient': recipient,
                'reference': idempotency_key,
                'source': 'LOAN_DISBURSEMENT',
                'metadata': {
                    'loan_id': metadata.get('application_id'),
                    'loan_type': metadata.get('loan_type'),
                    'farmer_id': metadata.get('farmer_id'),
                    'recipient_type': metadata.get('recipient_type', 'farmer'),
                }
            }
            
            # ClickPesa API endpoint for disbursement
            url = f"{self.base_url}/api/v1/disbursements"
            
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            
            if self._is_success(response):
                data = response.json()
                return {
                    'status': 'success',
                    'reference': data.get('reference', idempotency_key),
                    'reason': 'Disbursement initiated successfully',
                    'data': data,
                }
            else:
                error_data = response.json() if response.text else {}
                return {
                    'status': 'failed',
                    'reference': '',
                    'reason': error_data.get('message', f'HTTP {response.status_code}'),
                    'data': error_data,
                }
                
        except requests.exceptions.Timeout:
            return {
                'status': 'pending',
                'reference': idempotency_key,
                'reason': 'Request timeout - awaiting callback',
            }
        except Exception as e:
            logger.exception(f"ClickPesa disbursement error: {str(e)}")
            return {
                'status': 'failed',
                'reference': '',
                'reason': str(e)[:255],
            }
    
    def request_payment(self, *, amount: Decimal, payer: str, reference: str, metadata: dict):
        """
        Request payment from farmer (for repayments) via USSD push.
        
        Args:
            amount: Amount to collect
            payer: Phone number of payer
            reference: Unique reference
            metadata: Additional data (loan_id, repayment_id, etc.)
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] ClickPesa payment request: {amount} from {payer}")
            return {
                'status': 'success',
                'reference': f'DRY-{reference[:10]}',
                'checkout_url': 'https://example.com/checkout',
                'ussd_push': True,
                'reason': 'Dry run mode',
            }
        
        try:
            payer = self._normalize_phone(payer)
            
            payload = {
                'amount': str(amount),
                'payer': payer,
                'reference': reference,
                'description': metadata.get('description', 'Loan repayment'),
                'metadata': {
                    'loan_id': metadata.get('loan_id'),
                    'repayment_id': metadata.get('repayment_id'),
                    'installment_number': metadata.get('installment_number'),
                }
            }
            
            # ClickPesa API endpoint for payment requests
            url = f"{self.base_url}/api/v1/payments/request"
            
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            
            if self._is_success(response):
                data = response.json()
                return {
                    'status': 'success',
                    'reference': data.get('reference', reference),
                    'checkout_url': data.get('checkout_url'),
                    'ussd_push': data.get('ussd_push', True),
                    'reason': 'Payment requested successfully',
                    'data': data,
                }
            else:
                error_data = response.json() if response.text else {}
                return {
                    'status': 'failed',
                    'reference': '',
                    'checkout_url': None,
                    'ussd_push': False,
                    'reason': error_data.get('message', f'HTTP {response.status_code}'),
                    'data': error_data,
                }
                
        except Exception as e:
            logger.exception(f"ClickPesa payment request error: {str(e)}")
            return {
                'status': 'failed',
                'reference': '',
                'checkout_url': None,
                'ussd_push': False,
                'reason': str(e)[:255],
            }
    
    def verify_payment(self, reference: str):
        """Verify payment status with ClickPesa"""
        if self.dry_run:
            return {'status': 'completed', 'reference': reference}
        
        try:
            url = f"{self.base_url}/api/v1/payments/{reference}"
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            
            if self._is_success(response):
                data = response.json()
                return {
                    'status': data.get('status', 'pending'),
                    'reference': reference,
                    'amount': data.get('amount'),
                    'confirmed_at': data.get('confirmed_at'),
                    'data': data,
                }
            else:
                return {'status': 'pending', 'reference': reference, 'error': 'Verification failed'}
                
        except Exception as e:
            logger.exception(f"ClickPesa verification error: {str(e)}")
            return {'status': 'pending', 'reference': reference, 'error': str(e)}
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature"""
        if not self.webhook_secret:
            return True
        
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)


def get_clickpesa_provider():
    """Get ClickPesa provider instance"""
    return ClickPesaProvider()