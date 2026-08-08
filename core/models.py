"""
All models combined in one file for simplicity.
"""
import uuid
import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator


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


class OrderStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    SHIPPED = 'SHIPPED', 'Shipped'
    DELIVERED = 'DELIVERED', 'Delivered'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'
    REFUNDED = 'REFUNDED', 'Refunded'


class LoanStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    DISBURSED = 'DISBURSED', 'Disbursed'
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
    """Farmers don't login - data from USSD"""
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=15, unique=True)
    national_id = models.CharField(max_length=30, blank=True, null=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Location
    region = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    ward = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    
    # Farm details
    farm_size_acres = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    primary_crop = models.CharField(max_length=80, blank=True)
    secondary_crop = models.CharField(max_length=80, blank=True)
    
    # Registration
    registered_via = models.CharField(max_length=10, default='USSD')
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"
    
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
    
    def __str__(self):
        return self.company_name


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
    institution = models.ForeignKey(FinancialInstitution, on_delete=models.CASCADE, related_name='loan_products')
    name = models.CharField(max_length=150)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)
    duration_months = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.institution.institution_name}"


class LoanApplication(BaseModel):
    """Loan application from farmer"""
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='loan_applications')
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='applications')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=LoanStatus.choices, default=LoanStatus.PENDING)
    purpose = models.TextField(blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.farmer.full_name} - {self.loan_product.name}"


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
    
    def __str__(self):
        return f"SMS to {self.recipient} - {self.status}"


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
        """Check if session is stale (older than 3 minutes)"""
        if self.status != USSDStatus.ACTIVE:
            return True
        age = (timezone.now() - self.updated_at).total_seconds()
        return age > 180  # 3 minutes timeout
    
    def mark_completed(self):
        """Mark session as completed"""
        self.status = USSDStatus.COMPLETED
        self.end_time = timezone.now()
        self.save(update_fields=['status', 'end_time', 'updated_at'])


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