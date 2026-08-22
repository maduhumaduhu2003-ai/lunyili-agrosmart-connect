# core/views_webhook.py

import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.conf import settings

logger = logging.getLogger(__name__)


@csrf_exempt
def clickpesa_webhook(request):
    """
    Handle ClickPesa webhook callbacks for:
    1. Disbursement confirmations
    2. Payment (repayment) confirmations
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Verify webhook signature if configured
        webhook_secret = getattr(settings, 'CLICKPESA_WEBHOOK_SECRET', '')
        if webhook_secret:
            signature = request.headers.get('X-Webhook-Signature', '')
            if not signature:
                return JsonResponse({'error': 'Missing signature'}, status=401)
            
            from .services.clickpesa_service import get_clickpesa_provider
            provider = get_clickpesa_provider()
            if not provider.verify_webhook_signature(request.body, signature):
                return JsonResponse({'error': 'Invalid signature'}, status=401)
        
        data = json.loads(request.body)
        logger.info(f"ClickPesa webhook received: {data}")
        
        event_type = data.get('event')
        reference = data.get('reference') or data.get('transaction_reference')
        status = data.get('status')
        
        # Handle disbursement events
        if event_type in ['disbursement', 'disbursement.success', 'disbursement.failed']:
            from .services.disbursement_service import handle_disbursement_callback
            result = handle_disbursement_callback(reference, status, data)
            return JsonResponse({'status': 'ok', 'record': str(result.pk)})
        
        # Handle payment (repayment) events
        elif event_type in ['payment', 'payment.confirmed', 'payment.failed']:
            from .services.repayment_service import confirm_payment, fail_payment
            
            if status in ['success', 'confirmed', 'completed']:
                result = confirm_payment(reference, data)
                return JsonResponse({'status': 'ok', 'record': str(result.pk)})
            elif status in ['failed', 'cancelled', 'reversed']:
                result = fail_payment(reference, data.get('reason', ''), data)
                return JsonResponse({'status': 'ok', 'record': str(result.pk)})
        
        # Acknowledge receipt
        return JsonResponse({'status': 'ok', 'event': event_type, 'received': True})
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.exception(f"Webhook error: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
def clickpesa_health(request):
    """Health check endpoint for ClickPesa webhook"""
    return JsonResponse({
        'status': 'ok',
        'service': 'ClickPesa Webhook',
        'timestamp': timezone.now().isoformat()
    })