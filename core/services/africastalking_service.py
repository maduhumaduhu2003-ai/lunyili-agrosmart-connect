"""
Africa's Talking Service - Handles USSD and SMS
"""

import json
import logging
import time
import requests

from django.conf import settings

from .session_service import USSDSessionService
from .ussd_engine import USSDEngine

logger = logging.getLogger(__name__)


class AfricaTalkingService:
    """Service for Africa's Talking SMS and USSD."""

    def __init__(self):
        # ============================================================
        # SMS LIVE CREDENTIALS
        # ============================================================
        self.username = getattr(settings, "AT_SMS_USERNAME", "")
        self.api_key = getattr(settings, "AT_SMS_API_KEY", "")
        self.sender_id = getattr(settings, "AT_SMS_SENDER_ID", "")
        self.dry_run = getattr(settings, "AT_SMS_DRY_RUN", False)

        # LIVE SMS endpoint
        self.base_url = "https://api.africastalking.com/version1"

    # ======================================================================
    # SMS
    # ======================================================================

    def send_sms(self, phone_number, message, sender_id=None):
        """Send SMS through Africa's Talking LIVE SMS API."""

        # ----------------------------------------------------------
        # Clean phone number
        # ----------------------------------------------------------
        phone = str(phone_number).replace("+", "").replace(" ", "").strip()

        if phone.startswith("0"):
            phone = "255" + phone[1:]
        elif not phone.startswith("255"):
            phone = "255" + phone

        # ----------------------------------------------------------
        # Sender ID
        # ----------------------------------------------------------
        sender_id = sender_id or self.sender_id

        logger.info(
            f"Sending LIVE SMS to {phone} from {sender_id}"
        )

        logger.info(
            f"SMS credentials: username={self.username}, "
            f"api_key_configured={bool(self.api_key)}, "
            f"sender_id={sender_id}"
        )

        logger.info(
            f"Message preview: {message[:100]}..."
        )

        # ----------------------------------------------------------
        # Dry run
        # ----------------------------------------------------------
        if self.dry_run:
            logger.info(
                f"DRY RUN - SMS to {phone}: {message[:100]}..."
            )

            return {
                "status": "queued",
                "dry_run": True,
            }

        # ----------------------------------------------------------
        # Validate credentials
        # ----------------------------------------------------------
        if not self.username:
            logger.error(
                "AT_SMS_USERNAME is missing"
            )

            return {
                "status": "error",
                "message": "AT_SMS_USERNAME is not configured",
            }

        if not self.api_key:
            logger.error(
                "AT_SMS_API_KEY is missing"
            )

            return {
                "status": "error",
                "message": "AT_SMS_API_KEY is not configured",
            }

        # ----------------------------------------------------------
        # API URL
        # ----------------------------------------------------------
        url = f"{self.base_url}/messaging"

        # ----------------------------------------------------------
        # Request payload
        # ----------------------------------------------------------
        payload = {
            "username": self.username,
            "to": phone,
            "message": message,
        }

        # Only send "from" if configured
        if sender_id:
            payload["from"] = sender_id

        headers = {
            "apiKey": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # ----------------------------------------------------------
        # Retry
        # ----------------------------------------------------------
        max_retries = 3

        for attempt in range(1, max_retries + 1):

            try:

                logger.info(
                    f"Attempt {attempt}/{max_retries} "
                    f"to send LIVE SMS to {phone}"
                )

                response = requests.post(
                    url,
                    headers=headers,
                    data=payload,
                    timeout=30,
                )

                logger.info(
                    f"Response status: {response.status_code}"
                )

                logger.info(
                    f"Response text: "
                    f"{response.text[:500]}"
                )

                # --------------------------------------------------
                # 401 Authentication
                # --------------------------------------------------
                if response.status_code == 401:

                    logger.error(
                        "Africa's Talking returned 401 Unauthorized. "
                        "Check LIVE SMS username and API key."
                    )

                    return {
                        "status": "error",
                        "message": (
                            "Africa's Talking authentication failed. "
                            "Check AT_SMS_USERNAME and AT_SMS_API_KEY."
                        ),
                    }

                # --------------------------------------------------
                # Parse JSON
                # --------------------------------------------------
                try:
                    result = response.json()

                except json.JSONDecodeError:

                    logger.error(
                        f"Invalid JSON response: "
                        f"{response.text[:500]}"
                    )

                    if attempt < max_retries:
                        time.sleep(2)
                        continue

                    return {
                        "status": "error",
                        "message": response.text[:200],
                    }

                # --------------------------------------------------
                # Success
                # --------------------------------------------------
                if response.status_code in (200, 201):

                    recipients = (
                        result
                        .get("SMSMessageData", {})
                        .get("Recipients", [])
                    )

                    if recipients:

                        recipient = recipients[0]

                        recipient_status = recipient.get(
                            "status",
                            ""
                        )

                        if recipient_status.lower() == "success":

                            logger.info(
                                f"LIVE SMS sent successfully "
                                f"to {phone}"
                            )

                            return {
                                "status": "sent",
                                "data": result,
                            }

                        error_message = recipient.get(
                            "message",
                            "Unknown recipient error"
                        )

                        logger.error(
                            f"SMS recipient failed: "
                            f"{error_message}"
                        )

                        return {
                            "status": "error",
                            "message": error_message,
                            "data": result,
                        }

                    logger.warning(
                        "Africa's Talking returned success "
                        "but no recipients."
                    )

                    return {
                        "status": "error",
                        "message": "No recipients returned",
                        "data": result,
                    }

                # --------------------------------------------------
                # Other API errors
                # --------------------------------------------------
                error_message = (
                    result.get("error")
                    or result.get("message")
                    or "Unknown Africa's Talking error"
                )

                logger.error(
                    f"SMS failed with HTTP "
                    f"{response.status_code}: "
                    f"{error_message}"
                )

                if attempt < max_retries:
                    time.sleep(2)
                    continue

                return {
                    "status": "error",
                    "message": error_message,
                    "data": result,
                }

            except requests.exceptions.Timeout:

                logger.error(
                    f"Timeout on attempt "
                    f"{attempt}/{max_retries}"
                )

                if attempt < max_retries:
                    time.sleep(2)
                    continue

                return {
                    "status": "error",
                    "message": "Request timeout",
                }

            except requests.exceptions.ConnectionError as exc:

                logger.error(
                    f"Connection error: {exc}"
                )

                if attempt < max_retries:
                    time.sleep(2)
                    continue

                return {
                    "status": "error",
                    "message": str(exc),
                }

            except Exception as exc:

                logger.exception(
                    f"Unexpected SMS error: {exc}"
                )

                return {
                    "status": "error",
                    "message": str(exc),
                }

        return {
            "status": "error",
            "message": "Max retries exceeded",
        }

    # ======================================================================
    # USSD Callback
    # ======================================================================

    def ussd_callback(
        self,
        session_id,
        phone_number,
        text,
        network_code=""
    ):
        """Handle USSD callback from Africa's Talking."""

        from ..models import USSDLog, USSDSession

        start_time = time.time()

        try:

            session = USSDSessionService.resolve_session(
                session_id=session_id,
                phone_number=phone_number,
                network_code=network_code,
            )

            engine = USSDEngine(
                session,
                phone_number
            )

            response_type, response_text = engine.step(text)

            execution_time = int(
                (time.time() - start_time) * 1000
            )

            USSDLog.objects.create(
                session=session,
                user_input=text,
                response=response_text,
                response_type=response_type,
                execution_time_ms=execution_time,
            )

            return response_type, response_text

        except Exception as exc:

            logger.exception(
                f"USSD Error: {exc}"
            )

            try:

                session = USSDSession.objects.get(
                    session_id=session_id
                )

                USSDLog.objects.create(
                    session=session,
                    user_input=text,
                    response=f"Error: {exc}",
                    response_type="END",
                    execution_time_ms=int(
                        (time.time() - start_time) * 1000
                    ),
                    error=str(exc),
                )

            except Exception as log_error:

                logger.error(
                    f"Error logging USSD: {log_error}"
                )

            return (
                "END",
                "Samahani, kuna tatizo. "
                "Jaribu tena baadaye."
            )