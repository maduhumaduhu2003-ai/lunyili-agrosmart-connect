"""
USSD Views - Handles incoming USSD requests
"""
import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .services.africastalking_service import AfricaTalkingService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def ussd_callback(request):
    """
    USSD callback endpoint for Africa's Talking
    """
    # Get data from request
    session_id = request.POST.get('sessionId', '')
    phone_number = request.POST.get('phoneNumber', '')
    text = request.POST.get('text', '')
    network_code = request.POST.get('networkCode', '')
    
    logger.info(f"USSD Request: session={session_id}, phone={phone_number}, text={text}")
    
    # Process using Africa's Talking service
    service = AfricaTalkingService()
    response_type, response_text = service.ussd_callback(
        session_id=session_id,
        phone_number=phone_number,
        text=text,
        network_code=network_code
    )
    
    # Return response in Africa's Talking format
    return HttpResponse(f"{response_type} {response_text}", content_type="text/plain")


@csrf_exempt
@require_http_methods(["POST"])
def sms_callback(request):
    """
    SMS callback endpoint for Africa's Talking
    (For receiving SMS replies)
    """
    # Get data
    data = request.POST.dict()
    logger.info(f"SMS Callback: {data}")
    
    # Process incoming SMS
    # You can add logic here for handling SMS replies
    
    return HttpResponse("OK", content_type="text/plain")