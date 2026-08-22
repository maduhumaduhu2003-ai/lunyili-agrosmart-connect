"""KYC provider boundary. No NIDA endpoint is implemented here."""
import re
from dataclasses import dataclass
from typing import Protocol


@dataclass
class KYCResult:
    status: str
    provider: str = ''
    reference: str = ''
    result: dict | None = None


class KYCProvider(Protocol):
    def verify_identity(self, *, national_id: str, full_name: str, date_of_birth):
        """Verify with an authorised provider configured by the deployment."""


def validate_nida_format(value: str) -> str | None:
    """Validate shape only; a valid shape does not establish ownership."""
    normalized = re.sub(r'[^0-9]', '', value or '')
    return normalized if len(normalized) == 20 else None


class UnconfiguredKYCProvider:
    """Explicitly pending until an authorised provider is configured."""
    def verify_identity(self, **kwargs):
        return KYCResult(status='PENDING', result={'reason': 'No authorised KYC provider configured'})


def get_kyc_provider():
    # A real authorised adapter can be selected by deployment configuration later.
    return UnconfiguredKYCProvider()


def verify_farmer_identity(farmer, provider=None):
    """Run an authorised adapter and persist only its verification metadata."""
    provider = provider or get_kyc_provider()
    result = provider.verify_identity(
        national_id=farmer.national_id,
        full_name=farmer.full_name,
        date_of_birth=farmer.date_of_birth,
    )
    farmer.kyc_status = result.status
    farmer.kyc_provider = result.provider
    farmer.kyc_reference = result.reference
    farmer.kyc_result = result.result or {}
    if result.status == 'VERIFIED':
        from django.utils import timezone
        farmer.kyc_verified_at = timezone.now()
    farmer.save(update_fields=['kyc_status', 'kyc_provider', 'kyc_reference', 'kyc_result', 'kyc_verified_at', 'updated_at'])
    return result
