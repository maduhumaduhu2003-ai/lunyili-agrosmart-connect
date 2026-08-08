"""
Africa's Talking Service - Handles USSD and SMS
"""
import json
import logging
import requests
from django.conf import settings
from .session_service import USSDSessionService
from .ussd_engine import USSDEngine

logger = logging.getLogger(__name__)


class AfricaTalkingService:
    """Service for Africa's Talking USSD and SMS"""
    
    def __init__(self):
        self.username = settings.AT_USERNAME
        self.api_key = settings.AT_API_KEY
        self.short_code = settings.AT_SHORT_CODE
        self.sender_id = settings.AT_SENDER_ID or "agrosmart"
        self.dry_run = settings.AT_SMS_DRY_RUN
        
        self.base_url = "https://api.africastalking.com/version1"
        self.headers = {
            "Api-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    def send_sms(self, phone_number, message, sender_id=None):
        """Send SMS via Africa's Talking"""
        phone = phone_number.replace('+', '').replace(' ', '')
        
        if sender_id is None:
            sender_id = "agrosmart"
        
        logger.info(f"Sending SMS to {phone} from {sender_id}")
        
        if self.dry_run:
            logger.info(f"DRY RUN - SMS to {phone}: {message}")
            return {"status": "queued", "dry_run": True}
        
        if not self.api_key:
            logger.error("Africa's Talking API key not configured")
            return {"status": "error", "message": "API key not configured"}
        
        try:
            url = f"{self.base_url}/messaging"
            
            payload = {
                "username": self.username,
                "to": phone,
                "message": message,
                "from": sender_id
            }
            
            headers = {
                "Api-Key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            response = requests.post(url, headers=headers, data=payload)
            result = response.json()
            
            if response.status_code == 201 or response.status_code == 200:
                recipients = result.get('SMSMessageData', {}).get('Recipients', [])
                if recipients and recipients[0].get('status') == 'Success':
                    logger.info(f"SMS sent to {phone} from {sender_id}")
                    return {"status": "sent", "data": result}
                else:
                    logger.error(f"SMS failed: {result}")
                    return {"status": "error", "message": result}
            else:
                logger.error(f"SMS failed: {result}")
                return {"status": "error", "message": result}
                
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return {"status": "error", "message": str(e)}

    # ======================================================================
    # USSD Callback - HII NI MUHIMU!
    # ======================================================================
    def ussd_callback(self, session_id, phone_number, text, network_code=""):
        """
        Handle USSD callback from Africa's Talking
        """
        from ..models import USSDLog, USSDSession
        import time
        
        start_time = time.time()
        
        try:
            # Get or create session
            session = USSDSessionService.resolve_session(
                session_id=session_id,
                phone_number=phone_number,
                network_code=network_code
            )
            
            # Process with USSD engine
            engine = USSDEngine(session, phone_number)
            response_type, response_text = engine.step(text)
            
            # Log interaction
            execution_time = int((time.time() - start_time) * 1000)
            USSDLog.objects.create(
                session=session,
                user_input=text,
                response=response_text,
                response_type=response_type,
                execution_time_ms=execution_time,
            )
            
            return response_type, response_text
            
        except Exception as e:
            logger.error(f"USSD Error: {str(e)}")
            
            # Log error
            try:
                session = USSDSession.objects.get(session_id=session_id)
                USSDLog.objects.create(
                    session=session,
                    user_input=text,
                    response=f"Error: {str(e)}",
                    response_type="END",
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    error=str(e),
                )
            except Exception as log_error:
                logger.error(f"Error logging USSD: {str(log_error)}")
            
            return "END", "Samahani, kuna tatizo. Jaribu tena baadaye."