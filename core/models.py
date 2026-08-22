"""
All models combined in one file for simplicity.
"""
import uuid
import random
import string
import logging
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger(__name__)


# ===================== BASE MODEL =====================
class BaseModel(models.Model):
    """Base model with common fields"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


# ===================== CONSTANTS =====================
class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrator'
    EXTENSION_OFFICER = 'EXTENSION_OFFICER', 'Extension Officer'
    FINANCIAL = 'FINANCIAL', 'Financial Institution'
    BUYER = 'BUYER', 'Buyer'
    SUPPLIER = 'SUPPLIER', 'Supplier'


class Gender(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'O', 'Other'


class VerificationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    VERIFIED = 'VERIFIED', 'Verified'
    REJECTED = 'REJECTED', 'Rejected'


class KYCStatus(models.TextChoices):
    PROVIDED = 'PROVIDED', 'NIDA provided'
    FORMAT_VALID = 'FORMAT_VALID', 'NIDA format valid'
    VERIFIED = 'VERIFIED', 'Identity verified'
    FAILED = 'FAILED', 'Identity verification failed'
    PENDING = 'PENDING', 'Verification pending'


class OrderStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    LOAN_PENDING = 'LOAN_PENDING', 'Loan pending'
    PAYMENT_PENDING = 'PAYMENT_PENDING', 'Payment pending'
    SUPPLIER_PAID = 'SUPPLIER_PAID', 'Supplier paid'
    PROCESSING = 'PROCESSING', 'Processing'
    SHIPPED = 'SHIPPED', 'Shipped'
    DISPATCHED = 'DISPATCHED', 'Dispatched'
    DELIVERED = 'DELIVERED', 'Delivered'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'
    REFUNDED = 'REFUNDED', 'Refunded'


class RepaymentStatus(models.TextChoices):
    UPCOMING = 'UPCOMING', 'Upcoming'
    DUE = 'DUE', 'Due'
    PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially paid'
    PAID = 'PAID', 'Paid'
    OVERDUE = 'OVERDUE', 'Overdue'


class PaymentTransactionStatus(models.TextChoices):
    INITIATED = 'PAYMENT_INITIATED', 'Payment initiated'
    PENDING = 'PAYMENT_PENDING', 'Payment pending'
    CONFIRMED = 'PAYMENT_CONFIRMED', 'Payment confirmed'
    FAILED = 'PAYMENT_FAILED', 'Payment failed'
    REVERSED = 'PAYMENT_REVERSED', 'Payment reversed'


class LoanStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under review'
    INFO_REQUIRED = 'INFO_REQUIRED', 'Information required'
    APPROVED = 'APPROVED', 'Approved'
    FARMER_ACCEPTED = 'FARMER_ACCEPTED', 'Farmer accepted'
    FARMER_DECLINED = 'FARMER_DECLINED', 'Farmer declined'
    DISBURSEMENT_PENDING = 'DISBURSEMENT_PENDING', 'Disbursement pending'
    REJECTED = 'REJECTED', 'Rejected'
    DISBURSED = 'DISBURSED', 'Disbursed'
    ACTIVE = 'ACTIVE', 'Active'
    PARTIALLY_REPAID = 'PARTIALLY_REPAID', 'Partially repaid'
    OVERDUE = 'OVERDUE', 'Overdue'
    FULLY_REPAID = 'FULLY_REPAID', 'Fully repaid'
    REPAID = 'REPAID', 'Repaid'
    DEFAULTED = 'DEFAULTED', 'Defaulted'


class SMSStatus(models.TextChoices):
    QUEUED = 'QUEUED', 'Queued'
    SENT = 'SENT', 'Sent'
    FAILED = 'FAILED', 'Failed'
    DELIVERED = 'DELIVERED', 'Delivered'


class USSDStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    TIMED_OUT = "TIMED_OUT", "Timed Out"


# ===================== USER MODEL =====================
class User(AbstractUser):
    """Custom User model - authentication by username"""
    ROLE_CHOICES = [
        (UserRole.ADMIN, 'Administrator'),
        (UserRole.EXTENSION_OFFICER, 'Extension Officer'),
        (UserRole.FINANCIAL, 'Financial Institution'),
        (UserRole.BUYER, 'Buyer'),
        (UserRole.SUPPLIER, 'Supplier'),
    ]
    
    phone = models.CharField(max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=UserRole.SUPPLIER)
    profile_photo = models.ImageField(upload_to='profiles/', blank=True, null=True)
    address = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.username
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username


# ===================== FARMER =====================

class Farmer(BaseModel):
    """Farmer - Data inajengwa hatua kwa hatua"""
    
    # ============================================================
    # A. IDENTITY & KYC
    # ============================================================
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=15, unique=True)
    national_id = models.CharField(max_length=30, blank=True, null=True)
    kyc_status = models.CharField(max_length=20, choices=KYCStatus.choices, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_provider = models.CharField(max_length=80, blank=True)
    kyc_reference = models.CharField(max_length=120, blank=True)
    kyc_result = models.JSONField(default=dict, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Location
    region = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    
    # ============================================================
    # B. FARM PROFILE
    # ============================================================
    farm_size_acres = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    farm_ownership = models.CharField(max_length=20, choices=[
        ('OWNED', 'Owned'),
        ('RENTED', 'Rented'),
        ('BOTH', 'Both'),
    ], blank=True)
    primary_crop = models.CharField(max_length=80, blank=True)
    secondary_crop = models.CharField(max_length=80, blank=True)
    years_farming = models.PositiveIntegerField(null=True, blank=True)
    production_season = models.CharField(max_length=50, blank=True)
    estimated_production = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Estimated production in kg")
    irrigation_type = models.CharField(max_length=20, choices=[
        ('RAIN_FED', 'Rain-fed'),
        ('IRRIGATION', 'Irrigation'),
        ('BOTH', 'Both'),
    ], blank=True)
    
    # ============================================================
    # C. FINANCIAL BEHAVIOUR
    # ============================================================
    has_bank_account = models.BooleanField(default=False)
    bank_name = models.CharField(max_length=100, blank=True)
    has_saccos_account = models.BooleanField(default=False)
    saccos_name = models.CharField(max_length=100, blank=True)
    has_mobile_money = models.BooleanField(default=False)
    mobile_money_provider = models.CharField(max_length=50, blank=True)
    payout_account_verified = models.BooleanField(default=False)
    previous_loan_history = models.TextField(blank=True)
    
    # ============================================================
    # D. LOAN ELIGIBILITY
    # ============================================================
    loan_eligibility_score = models.IntegerField(default=0)
    loan_eligibility_level = models.CharField(max_length=20, blank=True)
    loan_eligibility_updated = models.DateTimeField(null=True, blank=True)
    is_loan_eligible = models.BooleanField(default=False)
    credit_readiness_score = models.IntegerField(default=0)
    
    # ============================================================
    # E. FARMER BEHAVIOUR (Kujaza Automatiki)
    # ============================================================
    total_orders_count = models.PositiveIntegerField(default=0)
    total_orders_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_market_transactions = models.PositiveIntegerField(default=0)
    total_sales_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    last_activity_date = models.DateTimeField(null=True, blank=True)
    profile_completeness = models.PositiveIntegerField(default=0)
    
    # Registration
    registered_via = models.CharField(max_length=10, default='USSD')
    is_active = models.BooleanField(default=True)
    
    # GPS
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    
    def calculate_credit_readiness(self):
        """Calculate credit readiness score (0-100)"""
        score = 0
        
        # 1. Identity/KYC completeness (15 points)
        if self.national_id: score += 5
        if self.date_of_birth: score += 5
        if self.gender: score += 3
        if self.village and self.district: score += 2
        
        # 2. Farm profile (15 points)
        if self.farm_size_acres and self.farm_size_acres >= 2: score += 5
        if self.primary_crop: score += 5
        if self.farm_ownership: score += 3
        if self.years_farming and self.years_farming >= 2: score += 2
        
        # 3. Farming experience (10 points)
        if self.years_farming:
            if self.years_farming >= 10: score += 10
            elif self.years_farming >= 5: score += 7
            elif self.years_farming >= 2: score += 4
            else: score += 2
        
        # 4. Input purchasing history (15 points)
        orders = Order.objects.filter(farmer=self)
        order_count = orders.count()
        if order_count >= 20: score += 15
        elif order_count >= 10: score += 12
        elif order_count >= 5: score += 8
        elif order_count >= 2: score += 5
        elif order_count >= 1: score += 2
        
        # 5. Crop/production history (15 points)
        if self.primary_crop: score += 5
        if self.estimated_production: score += 5
        if self.production_season: score += 3
        if self.secondary_crop: score += 2
        
        # 6. Market/sales history (10 points)
        market_activities = InterestedFarmer.objects.filter(farmer=self).count()
        if market_activities >= 5: score += 10
        elif market_activities >= 3: score += 7
        elif market_activities >= 1: score += 4
        
        # 7. Previous loan repayment (15 points)
        applications = LoanApplication.objects.filter(farmer=self)
        total_loans = applications.count()
        if total_loans > 0:
            repaid = applications.filter(status__in=['FULLY_REPAID', 'REPAID']).count()
            if repaid == total_loans:
                score += 15
            elif repaid >= total_loans * 0.7:
                score += 10
            elif repaid >= total_loans * 0.4:
                score += 5
        
        # 8. Profile consistency (5 points)
        if self.profile_completeness >= 80: score += 5
        elif self.profile_completeness >= 50: score += 3
        
        self.credit_readiness_score = min(score, 100)
        
        # Determine level
        if self.credit_readiness_score >= 90:
            level = 'VERY_STRONG'
            label = 'Profile Imara Sana'
        elif self.credit_readiness_score >= 75:
            level = 'STRONG'
            label = 'Profile Imara'
        elif self.credit_readiness_score >= 60:
            level = 'MODERATE'
            label = 'Profile Wastani'
        elif self.credit_readiness_score >= 40:
            level = 'LIMITED'
            label = 'Inahitaji Kuboreshwa'
        else:
            level = 'INCOMPLETE'
            label = 'Haijakamilika'
        
        self.loan_eligibility_level = level
        self.loan_eligibility_score = self.credit_readiness_score
        # Readiness is an indicator only; each loan product supplies its own threshold.
        self.is_loan_eligible = self.credit_readiness_score > 0
        self.loan_eligibility_updated = timezone.now()
        self.save()
        
        return self.credit_readiness_score
    
    def update_profile_completeness(self):
        """Update profile completeness percentage"""
        fields = [
            bool(self.full_name),
            bool(self.phone_number),
            bool(self.national_id),
            bool(self.gender),
            bool(self.date_of_birth),
            bool(self.region and self.district and self.village),
            bool(self.farm_size_acres),
            bool(self.primary_crop),
            bool(self.years_farming),
            bool(self.has_bank_account or self.has_saccos_account),
        ]
        total_fields = len(fields)
        filled = sum(fields)
        self.profile_completeness = int((filled / total_fields) * 100)
        self.save(update_fields=['profile_completeness'])
        return self.profile_completeness
    
    def get_eligibility_level(self):
        """Get eligibility level details"""
        score = self.credit_readiness_score
        if score >= 90:
            return {
                'level': 'VERY_STRONG',
                'label': 'Profile Imara Sana',
                'recommendation': 'Anapewa mkopo kwa urahisi',
                'max_multiplier': 1.0,
                'min_multiplier': 0.8,
            }
        elif score >= 75:
            return {
                'level': 'STRONG',
                'label': 'Profile Imara',
                'recommendation': 'Anapewa mkopo kwa masharti mazuri',
                'max_multiplier': 0.9,
                'min_multiplier': 0.6,
            }
        elif score >= 60:
            return {
                'level': 'MODERATE',
                'label': 'Profile Wastani',
                'recommendation': 'Anapewa mkopo kwa masharti ya kawaida',
                'max_multiplier': 0.7,
                'min_multiplier': 0.4,
            }
        elif score >= 40:
            return {
                'level': 'LIMITED',
                'label': 'Inahitaji Kuboreshwa',
                'recommendation': 'Anapewa mkopo mdogo kwa kuanzia',
                'max_multiplier': 0.5,
                'min_multiplier': 0.3,
            }
        else:
            return {
                'level': 'INCOMPLETE',
                'label': 'Haijakamilika',
                'recommendation': 'Anapendekezwa kuanza kuagiza na kukamilisha taarifa',
                'max_multiplier': 0.3,
                'min_multiplier': 0.1,
            }

    @property
    def location_summary(self):
        parts = []
        if self.village:
            parts.append(self.village)
        if self.ward:
            parts.append(self.ward)
        if self.district:
            parts.append(self.district)
        if self.region:
            parts.append(self.region)
        return ", ".join(parts) if parts else "Not set"

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"


# ===================== SUPPLIER =====================
class Supplier(BaseModel):
    """Supplier/Agro-dealer"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='supplier_profile')
    company_name = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to='suppliers/', blank=True, null=True)
    is_verified = models.CharField(max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    
    # ============================================================
    # O N G E Z A   H I Z I   F I E L D S
    # ============================================================
    region = models.CharField(max_length=100, blank=True, help_text="Mkoa wa supplier")
    district = models.CharField(max_length=100, blank=True, help_text="Wilaya ya supplier")
    ward = models.CharField(max_length=100, blank=True, help_text="Kata ya supplier")
    village = models.CharField(max_length=100, blank=True, help_text="Kijiji cha supplier")
    
    latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True,
        help_text="Latitude ya eneo la supplier"
    )
    longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True,
        help_text="Longitude ya eneo la supplier"
    )
    
    def __str__(self):
        return self.company_name
    
    @property
    def location_summary(self):
        """Get full location summary"""
        parts = []
        if self.village:
            parts.append(self.village)
        if self.ward:
            parts.append(self.ward)
        if self.district:
            parts.append(self.district)
        if self.region:
            parts.append(self.region)
        return ", ".join(parts) if parts else "Not set"


# ===================== BUYER =====================
class Buyer(BaseModel):
    """Buyer/Customer"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='buyer_profile')
    company_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_verified = models.CharField(max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    
    def __str__(self):
        return self.company_name or self.user.username


# ===================== EXTENSION OFFICER =====================
class ExtensionOfficer(BaseModel):
    """Extension Officer profile"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='officer_profile')
    region = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    employer = models.CharField(max_length=150, blank=True)
    position = models.CharField(max_length=100, blank=True)
    qualification = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return self.user.full_name


# ===================== FINANCIAL INSTITUTION =====================
class FinancialInstitution(BaseModel):
    """Bank/SACCOS/MFI"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='financial_profile')
    institution_name = models.CharField(max_length=200)
    institution_type = models.CharField(max_length=20, choices=[
        ('BANK', 'Bank'),
        ('SACCOS', 'SACCOS'),
        ('MFI', 'Microfinance'),
    ])
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='finance/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    
    def __str__(self):
        return self.institution_name


# ===================== PRODUCT =====================
class Category(BaseModel):
    """Product category"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.ImageField(upload_to='categories/', blank=True, null=True)
    
    def __str__(self):
        return self.name


class Product(BaseModel):
    """Product sold by supplier"""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='products')
    
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, default='kg')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.supplier.company_name}"


# ===================== ORDER =====================
class Order(BaseModel):
    """Order from farmer to supplier"""
    reference = models.CharField(max_length=30, unique=True, blank=True)
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='orders')
    
    # Ongeza hii - quantity_unit
    quantity_unit = models.CharField(max_length=20, default='kg')  # kg, bags, pieces, litres
    
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    delivery_address = models.TextField(blank=True)
    delivery_notes = models.TextField(blank=True)
    order_date = models.DateTimeField(default=timezone.now)
    delivered_date = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"ORD-{timezone.now().strftime('%Y%m')}-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.reference} - {self.farmer.full_name}"


class OrderItem(BaseModel):
    """Items in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    
    @property
    def subtotal(self):
        return self.price * self.quantity
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


# ===================== LOAN =====================
class LoanProduct(BaseModel):
    """Loan product from financial institution"""
    
    # ============================================================
    # LOAN TYPE CHOICES - HAPA NDIO CHOICES ZA LOAN TYPE
    # ============================================================
    class LoanType(models.TextChoices):
        GENERAL = 'GENERAL', 'Mkopo wa Jumla'
        INPUT = 'INPUT', 'Mkopo wa Pembejeo'
        PRODUCTION = 'PRODUCTION', 'Mkopo wa Uzalishaji'
        MARKET = 'MARKET', 'Mkopo wa Biashara ya Mazao'
    
    class RepaymentFrequency(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Kila Wiki'
        BIWEEKLY = 'BIWEEKLY', 'Kila Wiki Mbili'
        MONTHLY = 'MONTHLY', 'Kila Mwezi'
        QUARTERLY = 'QUARTERLY', 'Kila Robo Mwaka'
    
    institution = models.ForeignKey(FinancialInstitution, on_delete=models.CASCADE, related_name='loan_products')
    name = models.CharField(max_length=150)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)
    duration_months = models.PositiveIntegerField()
    
    # ============================================================
    # FIXED: loan_type with choices
    # ============================================================
    loan_type = models.CharField(
        max_length=20, 
        choices=LoanType.choices,
        default=LoanType.GENERAL
    )
    
    # ============================================================
    # FIXED: repayment_frequency with choices
    # ============================================================
    repayment_frequency = models.CharField(
        max_length=20, 
        choices=RepaymentFrequency.choices,
        default=RepaymentFrequency.MONTHLY
    )
    
    grace_period_days = models.PositiveIntegerField(default=0)
    minimum_credit_score = models.PositiveIntegerField(default=40, help_text="Minimum credit readiness score required (0-100)")
    eligibility_rules = models.JSONField(default=dict, blank=True)
    required_profile_information = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.institution.institution_name}"


class LoanApplication(BaseModel):
    """Loan application from farmer"""
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='loan_applications')
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='applications')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=25, choices=LoanStatus.choices, default=LoanStatus.PENDING)
    purpose = models.TextField(blank=True)
    order = models.OneToOneField(
        Order, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='loan_application'
    )
    approved_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_loan_applications'
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    acceptance_status = models.CharField(max_length=20, blank=True)
    accepted_terms_version = models.CharField(max_length=40, blank=True)
    acceptance_session_reference = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['farmer', 'loan_product'],
                condition=models.Q(status__in=['PENDING', 'UNDER_REVIEW', 'INFO_REQUIRED', 'APPROVED', 'FARMER_ACCEPTED', 'DISBURSEMENT_PENDING']),
                name='one_active_application_per_product',
            ),
        ]
    
    def __str__(self):
        return f"{self.farmer.full_name} - {self.loan_product.name}"


class Loan(BaseModel):
    """A loan created only after an application is approved and disbursed."""
    application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, related_name='loan')
    principal_amount = models.DecimalField(max_digits=14, decimal_places=2)
    interest_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    outstanding_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=25, choices=LoanStatus.choices, default=LoanStatus.DISBURSEMENT_PENDING)

    @property
    def total_payable(self):
        return self.principal_amount + self.interest_amount


class Repayment(BaseModel):
    """A scheduled or recorded repayment against a disbursed loan."""
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='repayments')
    installment_number = models.PositiveIntegerField(null=True, blank=True)
    due_date = models.DateField()
    principal_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    interest_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=RepaymentStatus.choices, default=RepaymentStatus.UPCOMING)

    @property
    def remaining_balance(self):
        return max(self.principal_due + self.interest_due - self.paid_amount, Decimal('0'))

    @property
    def is_overdue(self):
        return self.remaining_balance > 0 and self.due_date < timezone.localdate()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['loan', 'installment_number'],
                name='unique_loan_installment',
            ),
        ]


class PaymentTransaction(BaseModel):
    """Provider payment record; confirmation is the only balance-changing event."""
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payment_transactions')
    repayment = models.ForeignKey(Repayment, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_transactions')
    provider = models.CharField(max_length=40, default='MANUAL_INSTRUCTION')
    provider_reference = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=25, choices=PaymentTransactionStatus.choices, default=PaymentTransactionStatus.INITIATED)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)


class LoanDisbursement(BaseModel):
    """Disbursement instruction and provider outcome; never proof of success by itself."""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        REVERSED = 'REVERSED', 'Reversed'

    application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, related_name='disbursement')
    loan = models.OneToOneField(Loan, on_delete=models.CASCADE, related_name='disbursement')
    provider = models.CharField(max_length=60)
    idempotency_key = models.CharField(max_length=120, unique=True)
    provider_reference = models.CharField(max_length=120, blank=True, null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    recipient = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    provider_result = models.JSONField(default=dict, blank=True)


class LoanDecisionAudit(BaseModel):
    """Immutable record of a financial institution decision."""
    application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='decision_audits')
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='loan_decision_audits')
    decision = models.CharField(max_length=30)
    notes = models.TextField(blank=True)


# ===================== ADVICE =====================
class Advice(BaseModel):
    """Farming advice from extension officer"""
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=50, choices=[
        ('CROP', 'Crop Management'),
        ('PEST', 'Pest Control'),
        ('DISEASE', 'Disease Control'),
        ('IRRIGATION', 'Irrigation'),
        ('FERTILIZER', 'Fertilizer'),
        ('GENERAL', 'General'),
    ])
    author = models.ForeignKey(ExtensionOfficer, on_delete=models.SET_NULL, null=True, related_name='advice')
    crop = models.CharField(max_length=100, blank=True, help_text="Specific crop if applicable")
    image = models.ImageField(upload_to='advice/', blank=True, null=True)
    published_date = models.DateTimeField(default=timezone.now)
    is_published = models.BooleanField(default=True)
    
    def __str__(self):
        return self.title


# ===================== WEATHER =====================
class WeatherData(BaseModel):
    """Weather data cached by region"""
    region = models.CharField(max_length=100, db_index=True)
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    humidity = models.PositiveIntegerField(null=True, blank=True)
    condition = models.CharField(max_length=100, blank=True)
    rain_probability = models.PositiveIntegerField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.region} - {self.fetched_at.strftime('%Y-%m-%d %H:%M')}"


class WeatherAlert(BaseModel):
    """Weather alerts issued by admin/officer"""
    region = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    message = models.TextField()
    severity = models.CharField(max_length=20, choices=[
        ('INFO', 'Information'),
        ('WARNING', 'Warning'),
        ('SEVERE', 'Severe'),
    ], default='INFO')
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.title} - {self.region}"


# ===================== MARKET =====================
class MarketPrice(BaseModel):
    """Market prices for crops"""
    crop = models.CharField(max_length=100)
    market = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, default='kg')
    price_date = models.DateField(default=timezone.now)
    source = models.CharField(max_length=20, default='MANUAL')
    
    def __str__(self):
        return f"{self.crop} @ {self.market}: {self.price} TZS"


class BuyingRequest(BaseModel):
    """Buyer wants to buy crops"""
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='buying_requests')
    crop = models.CharField(max_length=100)
    quantity_kg = models.PositiveIntegerField()
    price_offered = models.DecimalField(max_digits=12, decimal_places=2)
    location = models.CharField(max_length=150)
    expiry_date = models.DateField()
    is_open = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.buyer.company_name} wants {self.quantity_kg}kg {self.crop}"


# ===================== SMS =====================

class SMSTemplate(BaseModel):
    """SMS message template"""
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=50)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name


class SMSMessage(BaseModel):
    """SMS message log"""
    recipient = models.CharField(max_length=15)
    message = models.TextField()
    template = models.ForeignKey(SMSTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=SMSStatus.choices, default=SMSStatus.QUEUED)
    provider = models.CharField(max_length=30, default='AFRICASTALKING')
    provider_message_id = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    cost = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    event_key = models.CharField(max_length=180, unique=True, null=True, blank=True)
    
    def __str__(self):
        return f"SMS to {self.recipient} - {self.status}"
    
    def mark_sent(self, provider_message_id='', provider_response=None, cost=None):
        """Mark SMS as sent"""
        self.status = SMSStatus.SENT
        self.provider_message_id = provider_message_id
        self.sent_at = timezone.now()
        if cost is not None:
            self.cost = cost
        self.save(update_fields=['status', 'provider_message_id', 'sent_at', 'cost', 'updated_at'])
        logger.info(f"SMS marked as sent: {self.id} to {self.recipient}")
        return True
    
    def mark_failed(self, error_message=''):
        """Mark SMS as failed"""
        self.status = SMSStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=['status', 'error_message', 'updated_at'])
        logger.error(f"SMS marked as failed: {self.id} to {self.recipient} - {error_message}")
        return True
    
    def mark_delivered(self):
        """Mark SMS as delivered"""
        self.status = SMSStatus.DELIVERED
        self.save(update_fields=['status', 'updated_at'])
        logger.info(f"SMS marked as delivered: {self.id} to {self.recipient}")
        return True
    
    def mark_queued(self):
        """Mark SMS as queued"""
        self.status = SMSStatus.QUEUED
        self.save(update_fields=['status', 'updated_at'])
        return True


# ===================== USSD =====================
class USSDSession(BaseModel):
    """USSD session tracking"""
    session_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=15, db_index=True)
    network_code = models.CharField(max_length=10, blank=True, null=True)
    menu_level = models.PositiveIntegerField(default=0)
    current_screen = models.CharField(max_length=50, default='main')
    state_data = models.JSONField(default=dict)
    last_input = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=USSDStatus.choices, default=USSDStatus.ACTIVE)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'ussd_sessions'
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.session_id} - {self.phone_number}"
    
    @property
    def is_stale(self):
        """Check if session is stale - extended timeout"""
        if self.status != USSDStatus.ACTIVE:
            return True
        
        # Get timeout from settings (default 30 minutes)
        timeout_seconds = getattr(settings, 'USSD_SESSION_TIMEOUT', 1800)
        age = (timezone.now() - self.updated_at).total_seconds()
        return age > timeout_seconds
    
    def extend_session(self):
        """Extend session lifetime"""
        self.updated_at = timezone.now()
        self.save(update_fields=['updated_at'])
        logger.info(f"Session {self.session_id} extended")
    
    def mark_completed(self):
        """Mark session as completed"""
        self.status = USSDStatus.COMPLETED
        self.end_time = timezone.now()
        self.save(update_fields=['status', 'end_time', 'updated_at'])
        logger.info(f"Session {self.session_id} marked as completed")


class USSDLog(BaseModel):
    """USSD request/response log"""
    session = models.ForeignKey(USSDSession, on_delete=models.CASCADE, related_name='logs')
    user_input = models.CharField(max_length=255, blank=True)
    response = models.TextField()
    response_type = models.CharField(max_length=10, default='CON')
    execution_time_ms = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    
    class Meta:
        db_table = 'ussd_logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.session.session_id} - {self.created_at}"


# ===================== INTERESTED FARMER =====================
class InterestedFarmer(BaseModel):
    """Track farmers interested in a buying request"""
    buying_request = models.ForeignKey(
        BuyingRequest, 
        on_delete=models.CASCADE, 
        related_name='interested_farmers'
    )
    farmer = models.ForeignKey(
        Farmer, 
        on_delete=models.CASCADE, 
        related_name='buying_interests'
    )
    is_contacted = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'interested_farmers'
        ordering = ['-created_at']
        unique_together = ['buying_request', 'farmer']
    
    def __str__(self):
        return f"{self.farmer.full_name} -> {self.buying_request.crop}"