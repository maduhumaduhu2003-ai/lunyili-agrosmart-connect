"""
USSD Views - Handles incoming USSD requests
"""
import logging
import time
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone

from .services.africastalking_service import AfricaTalkingService
from .models import SMSMessage, Farmer, LoanApplication, Order, PaymentTransactionStatus
from .services.session_service import USSDSessionService
from .services.notification_service import send_event_sms
from .services.repayment_service import confirm_payment, fail_payment
from .services.disbursement_service import handle_disbursement_callback

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ussd_callback(request):
    """
    USSD callback endpoint for Africa's Talking
    Extended session timeout: 30 minutes
    """
    start_time = time.time()
    
    # Get data from request
    if request.method == 'POST':
        session_id = request.POST.get('sessionId', '')
        phone_number = request.POST.get('phoneNumber', '')
        text = request.POST.get('text', '')
        network_code = request.POST.get('networkCode', '')
    else:
        session_id = request.GET.get('sessionId', '')
        phone_number = request.GET.get('phoneNumber', '')
        text = request.GET.get('text', '')
        network_code = request.GET.get('networkCode', '')
    
    logger.info(f"USSD Request: session={session_id}, phone={phone_number}, text='{text}'")
    
    # If no session_id, return test response
    if not session_id:
        return HttpResponse("CON Karibu Lunyili AgroSmart\n1. Jisajili\n2. Agiza Pembejeo", content_type="text/plain")
    
    # Process using Africa's Talking service
    try:
        service = AfricaTalkingService()
        response_type, response_text = service.ussd_callback(
            session_id=session_id,
            phone_number=phone_number,
            text=text,
            network_code=network_code
        )
        
        # Log response time
        elapsed_time = (time.time() - start_time) * 1000
        logger.info(f"USSD Response: {response_type} - {response_text[:50]}... ({elapsed_time:.0f}ms)")
        
        # Return response in Africa's Talking format
        return HttpResponse(f"{response_type} {response_text}", content_type="text/plain")
        
    except Exception as e:
        logger.error(f"USSD Error: {str(e)}")
        return HttpResponse(f"END Samahani, kuna tatizo. Jaribu tena baadaye.", content_type="text/plain")


@csrf_exempt
@require_http_methods(["POST"])
def sms_callback(request):
    """
    SMS callback endpoint for Africa's Talking
    URL: https://greeter-copier-connector.ngrok-free.dev/sms-callback/
    """
    # Get data from Africa's Talking
    data = request.POST.dict()
    logger.info(f"SMS Callback Received: {data}")
    
    from_number = data.get('from', '')
    to_number = data.get('to', '')
    message = data.get('text', '')
    message_id = data.get('id', '')
    
    logger.info(f"SMS from {from_number} to {to_number}: {message}")
    
    if from_number and message:
        # Save incoming SMS
        try:
            sms = SMSMessage.objects.create(
                recipient=to_number,
                message=f"Reply from {from_number}: {message}",
                status='DELIVERED',
                provider='AFRICASTALKING',
                provider_message_id=message_id,
                sent_at=timezone.now()
            )
            logger.info(f"Incoming SMS saved: {sms.id}")
        except Exception as e:
            logger.error(f"Error saving incoming SMS: {str(e)}")
        
        # Process the SMS based on content
        response = process_incoming_sms(from_number, message)
        
        # Send auto-reply if needed
        if response:
            try:
                service = AfricaTalkingService()
                service.send_sms(from_number, response, sender_id="AGROSMART")
                logger.info(f"Auto-reply sent to {from_number} from AGROSMART")
            except Exception as e:
                logger.error(f"Error sending auto-reply: {str(e)}")
    
    # Africa's Talking inatarajia response "OK"
    return HttpResponse("OK", content_type="text/plain")


@csrf_exempt
@require_http_methods(["POST"])
def payment_callback(request):
    """Confirm a provider payment only after the provider callback."""
    provider_reference = request.POST.get('provider_reference') or request.POST.get('transaction_id')
    if not provider_reference:
        return JsonResponse({'status': 'error', 'message': 'Missing payment reference'}, status=400)

    try:
        payload = request.POST.dict()
        provider_status = (payload.get('status') or payload.get('result') or '').lower()
        if provider_status in ['failed', 'failure', 'cancelled', 'canceled']:
            payment = fail_payment(provider_reference, provider_status, payload)
        elif provider_status not in ['success', 'successful', 'confirmed', 'completed']:
            return JsonResponse({'status': PaymentTransactionStatus.PENDING, 'reference': provider_reference})
        else:
            payment = confirm_payment(provider_reference, payload)
    except Exception:
        logger.exception('Payment callback processing failed')
        return JsonResponse({'status': 'error'}, status=500)

    if payment.status == PaymentTransactionStatus.CONFIRMED:
        farmer = payment.loan.application.farmer
        send_event_sms(
            f'payment-received-{payment.id}', farmer.phone_number,
            f'Lunyili AgroSmart: Malipo ya TSh {int(payment.amount):,} yamepokelewa. '
            f'Baki: TSh {int(payment.loan.outstanding_balance):,}.',
        )
        if payment.loan.status == 'REPAID':
            send_event_sms(
                f'loan-repaid-{payment.loan.id}', farmer.phone_number,
                'Lunyili AgroSmart: Hongera, mkopo wako umelipwa kikamilifu.',
            )
    return JsonResponse({'status': payment.status, 'reference': payment.provider_reference})


@csrf_exempt
@require_http_methods(["POST"])
def disbursement_callback(request):
    """Provider webhook for loan disbursements; signature verification belongs to its adapter."""
    provider_reference = request.POST.get('provider_reference') or request.POST.get('transaction_id')
    provider_status = request.POST.get('status') or request.POST.get('result')
    if not provider_reference or not provider_status:
        return JsonResponse({'status': 'error', 'message': 'Missing disbursement reference or status'}, status=400)
    try:
        record = handle_disbursement_callback(provider_reference, provider_status, request.POST.dict())
    except Exception:
        logger.exception('Disbursement callback processing failed')
        return JsonResponse({'status': 'error'}, status=500)
    return JsonResponse({'status': record.status, 'reference': record.provider_reference})


def process_incoming_sms(phone_number, message):
    """Process incoming SMS and generate response"""
    try:
        farmer = Farmer.objects.filter(phone_number=phone_number).first()
    except:
        farmer = None
    
    if not farmer:
        return "Samahani, namba yako haijasajiliwa. Tafadhali jisajili kupitia *566#."
    
    message_lower = message.lower().strip()
    
    if 'help' in message_lower or 'saidia' in message_lower:
        return (
            "Karibu Lunyili AgroSmart!\n"
            "Huduma zinapatikana kupitia *566#\n"
            "Au tembelea ofisi yetu kwa msaada."
        )
    
    elif 'status' in message_lower or 'hali' in message_lower:
        applications = LoanApplication.objects.filter(farmer=farmer).order_by('-created_at')[:3]
        
        if applications.exists():
            response = "Hali ya Mikopo Yako:\n"
            for app in applications:
                response += f"- {app.loan_product.name}: {app.get_status_display()}\n"
            return response
        else:
            return "Hujawahi kuomba mkopo. Piga *566# kuomba."
    
    elif 'order' in message_lower or 'agizo' in message_lower:
        orders = Order.objects.filter(farmer=farmer).order_by('-created_at')[:3]
        
        if orders.exists():
            response = "Agizo Lako:\n"
            for order in orders:
                response += f"- #{order.reference}: {order.get_status_display()}\n"
            return response
        else:
            return "Hujawahi kuagiza. Piga *566# kuagiza."
    
    elif 'hello' in message_lower or 'habari' in message_lower:
        return f"Habari {farmer.full_name}! Karibu tena. Piga *566# kwa huduma."
    
    else:
        return (
            f"Asante kwa ujumbe wako, {farmer.full_name}!\n"
            "Tutakujibu hivi karibuni.\n"
            "Piga *566# kwa huduma za haraka."
        )


# ======================================================================
# SESSION MANAGEMENT HELPERS
# ======================================================================

def extend_session(session_id):
    """
    Extend USSD session lifetime
    """
    try:
        from .models import USSDSession
        session = USSDSession.objects.get(session_id=session_id)
        session.updated_at = timezone.now()
        session.save(update_fields=['updated_at'])
        logger.info(f"Session {session_id} extended")
        return True
    except Exception as e:
        logger.error(f"Error extending session: {str(e)}")
        return False


def get_session_timeout():
    """
    Get session timeout from settings
    Default: 30 minutes (1800 seconds)
    """
    return getattr(settings, 'USSD_SESSION_TIMEOUT', 1800)


def is_session_valid(session_id):
    """
    Check if session is still valid
    """
    try:
        from .models import USSDSession
        from django.utils import timezone
        session = USSDSession.objects.get(session_id=session_id)
        timeout = get_session_timeout()
        age = (timezone.now() - session.updated_at).total_seconds()
        return age < timeout and session.status == 'ACTIVE'
    except:
        return False