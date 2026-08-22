"""
USSD Session Service - Handles session management
"""
from __future__ import annotations
import logging
from django.utils import timezone
from django.conf import settings
from ..models import USSDSession, USSDStatus

logger = logging.getLogger(__name__)


class USSDSessionService:
    """Service for managing USSD sessions"""
    
    # Session timeout in seconds (default 30 minutes)
    SESSION_TIMEOUT_SECONDS = getattr(settings, 'USSD_SESSION_TIMEOUT', 1800)
    
    @staticmethod
    def resolve_session(session_id: str, phone_number: str, network_code: str = "") -> USSDSession:
        """Get or create a USSD session"""
        try:
            session = USSDSession.objects.get(session_id=session_id)
            
            # Update phone number if different
            if session.phone_number != phone_number:
                session.phone_number = phone_number
            
            # Update network code if provided
            if network_code and session.network_code != network_code:
                session.network_code = network_code
            
            # Check if session is stale or completed
            if session.status != USSDStatus.ACTIVE:
                # Reset session to main menu
                session.status = USSDStatus.ACTIVE
                session.current_screen = 'main'
                session.state_data = {}
                session.last_input = ''
                session.menu_level = 0
                session.end_time = None
                session.save()
                logger.info(f"Session {session_id} reset to main menu (was {session.status}")
            elif session.is_stale:
                # Session expired - reset
                session.current_screen = 'main'
                session.state_data = {}
                session.last_input = ''
                session.menu_level = 0
                session.save()
                logger.info(f"Session {session_id} stale, reset to main menu")
                
            # Update last activity - use updated_at field (from BaseModel)
            session.updated_at = timezone.now()
            session.save(update_fields=['updated_at'])
                
            return session
            
        except USSDSession.DoesNotExist:
            # Create new session
            session = USSDSession.objects.create(
                session_id=session_id,
                phone_number=phone_number,
                network_code=network_code or '',
                current_screen='main',
                state_data={},
                status=USSDStatus.ACTIVE,
                start_time=timezone.now()
            )
            logger.info(f"New session created: {session_id}")
            return session
    
    @staticmethod
    def save_state(session: USSDSession, current_screen: str, state_data: dict, last_input: str):
        """Save session state with updated timestamp"""
        session.current_screen = current_screen
        session.state_data = state_data
        session.last_input = last_input
        session.menu_level = state_data.get('_menu_level', 0)
        session.updated_at = timezone.now()  # Use updated_at instead of last_updated
        session.save(update_fields=['current_screen', 'state_data', 'last_input', 'menu_level', 'updated_at'])
    
    @staticmethod
    def end_session(session: USSDSession):
        """End a USSD session"""
        session.status = USSDStatus.COMPLETED
        session.end_time = timezone.now()
        session.updated_at = timezone.now()
        session.save(update_fields=['status', 'end_time', 'updated_at'])
        logger.info(f"Session {session.session_id} completed")