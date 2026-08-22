import logging

from ..models import SMSMessage, SMSStatus

logger = logging.getLogger(__name__)


def send_event_sms(event_key, phone_number, message):
    """Queue and send one idempotent business-event SMS."""
    sms, created = SMSMessage.objects.get_or_create(
        event_key=event_key,
        defaults={
            'recipient': phone_number,
            'message': message,
            'status': SMSStatus.QUEUED,
        },
    )
    if not created and sms.status in [SMSStatus.SENT, SMSStatus.DELIVERED]:
        return sms

    try:
        from .africastalking_service import AfricaTalkingService
        result = AfricaTalkingService().send_sms(phone_number, message)
        if result.get('status') == 'sent':
            recipients = result.get('data', {}).get('SMSMessageData', {}).get('Recipients', [])
            recipient = recipients[0] if recipients else {}
            sms.mark_sent(
                provider_message_id=recipient.get('messageId', ''),
                cost=recipient.get('cost'),
            )
        elif result.get('status') == 'queued':
            sms.status = SMSStatus.QUEUED
            sms.error_message = ''
            sms.save(update_fields=['status', 'error_message', 'updated_at'])
        else:
            sms.mark_failed(result.get('message', 'SMS provider failed'))
    except Exception as exc:
        logger.exception('Business SMS failed for event %s', event_key)
        sms.mark_failed(str(exc)[:255])
    return sms
