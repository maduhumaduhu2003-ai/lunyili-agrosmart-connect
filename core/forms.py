from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    User,
    Product,
    Category,
    Supplier,
    Buyer,
    BuyingRequest,
    ExtensionOfficer,
    Advice,
    FinancialInstitution,
    LoanProduct,
    LoanApplication,
)


# ============================================================================
# COMMON HELPERS
# ============================================================================

def add_form_control(field):
    """
    Add consistent Bootstrap classes to form fields.
    """
    widget = field.widget

    if isinstance(widget, forms.Select):
        widget.attrs["class"] = "form-select"
    elif isinstance(widget, forms.CheckboxInput):
        widget.attrs["class"] = "form-check-input"
    else:
        widget.attrs["class"] = "form-control"


# ============================================================================
# AUTHENTICATION
# ============================================================================

class RegisterForm(UserCreationForm):
    """
    User registration form.

    Password restrictions are intentionally disabled.
    """

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your email",
                "autocomplete": "email",
            }
        ),
    )

    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your first name",
                "autocomplete": "given-name",
            }
        ),
    )

    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your last name",
                "autocomplete": "family-name",
            }
        ),
    )

    phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your phone number (optional)",
                "autocomplete": "tel",
            }
        ),
    )

    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        required=True,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            add_form_control(field)

        # Username
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Enter your username",
                "autocomplete": "username",
            }
        )

        # Passwords
        self.fields["password1"].widget.attrs.update(
            {
                "placeholder": "Enter your password",
                "autocomplete": "new-password",
            }
        )

        self.fields["password2"].widget.attrs.update(
            {
                "placeholder": "Confirm your password",
                "autocomplete": "new-password",
            }
        )

        # Remove default Django password help text.
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

        # Disable Django's default password validators.
        self.fields["password1"].validators = []
        self.fields["password2"].validators = []

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "A user with this email already exists."
            )

        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")

        if phone and User.objects.filter(phone=phone).exists():
            raise ValidationError(
                "A user with this phone number already exists."
            )

        return phone

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")

        if not password1:
            raise ValidationError("Password cannot be empty.")

        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match.")

        return password2

    def save(self, commit=True):
        user = super().save(commit=False)

        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]

        # Admin users automatically receive staff/superuser privileges.
        if user.role == "ADMIN":
            user.is_staff = True
            user.is_superuser = True

        if commit:
            user.save()

        return user


class LoginForm(AuthenticationForm):
    """
    Login form.
    """

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your username",
                "autocomplete": "username",
            }
        )
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        )
    )

    def clean(self):
        cleaned_data = super().clean()

        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if username and password:
            user = authenticate(
                username=username,
                password=password,
            )

            if user is None:
                raise ValidationError(
                    "Invalid username or password."
                )

            if not user.is_active:
                raise ValidationError(
                    "This account is inactive. Please contact support."
                )

            self.user_cache = user

        return cleaned_data


# ============================================================================
# USER PROFILE
# ============================================================================

class UserProfileForm(forms.ModelForm):
    """
    Form for updating user profile.
    """

    class Meta:
        model = User

        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "profile_photo",
        ]

        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "First name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Last name",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Email address",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Phone number",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Your address",
                }
            ),
            "profile_photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if (
            email
            and User.objects.exclude(pk=self.instance.pk)
            .filter(email__iexact=email)
            .exists()
        ):
            raise ValidationError(
                "A user with this email already exists."
            )

        return email


# ============================================================================
# PRODUCT
# ============================================================================

class ProductForm(forms.ModelForm):
    """
    Form for creating/editing products.
    """

    class Meta:
        model = Product

        fields = [
            "category",
            "name",
            "description",
            "price",
            "stock",
            "unit",
            "image",
            "is_available",
        ]

        widgets = {
            "category": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter product name",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Product description",
                }
            ),
            "price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Price in TSh",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "stock": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Quantity in stock",
                    "min": "0",
                }
            ),
            "unit": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. kg, piece, bag",
                }
            ),
            "image": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "is_available": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].required = True
        self.fields["name"].required = True
        self.fields["price"].required = True
        self.fields["stock"].required = True

    def clean_price(self):
        price = self.cleaned_data.get("price")

        if price is not None and price < 0:
            raise ValidationError(
                "Price cannot be negative."
            )

        return price

    def clean_stock(self):
        stock = self.cleaned_data.get("stock")

        if stock is not None and stock < 0:
            raise ValidationError(
                "Stock cannot be negative."
            )

        return stock


# ============================================================================
# SUPPLIER PROFILE
# ============================================================================

class SupplierProfileForm(forms.ModelForm):
    """
    Form for creating/updating supplier profile.

    Phone and email are stored in User,
    therefore they are intentionally excluded here.
    """

    class Meta:
        model = Supplier

        fields = [
            "company_name",
            "registration_number",
            "address",
            "location",
            "region",
            "district",
            "ward",
            "village",
            "logo",
        ]

        widgets = {
            "company_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter company name",
                }
            ),
            "registration_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Business registration number",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Physical address",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "City / Area",
                }
            ),
            "region": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Mfano: Morogoro, Dar es Salaam",
                }
            ),
            "district": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Mfano: Mvomero, Kinondoni",
                }
            ),
            "ward": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Mfano: Dakawa, Mikocheni",
                }
            ),
            "village": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Mfano: Dakawa, Mbezi",
                }
            ),
            "logo": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["company_name"].required = True
        self.fields["region"].required = True
        self.fields["district"].required = True

        self.fields["region"].help_text = (
            "Mkoa ulipo (Mfano: Morogoro)"
        )

        self.fields["district"].help_text = (
            "Wilaya ulipo (Mfano: Mvomero)"
        )

        self.fields["ward"].help_text = (
            "Kata ulipo (Si lazima)"
        )

        self.fields["village"].help_text = (
            "Kijiji ulipo (Si lazima)"
        )


# ============================================================================
# BUYER PROFILE
# ============================================================================

class BuyerProfileForm(forms.ModelForm):
    """
    Form for creating/updating buyer profile.

    Phone and email are stored in User.
    """

    class Meta:
        model = Buyer

        fields = [
            "company_name",
            "location",
        ]

        widgets = {
            "company_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Company name (optional)",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your location / region",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["company_name"].required = False
        self.fields["location"].required = True


# ============================================================================
# EXTENSION OFFICER PROFILE
# ============================================================================

class ExtensionOfficerProfileForm(forms.ModelForm):
    """
    Form for creating/updating extension officer profile.

    Phone and email are stored in User.
    """

    class Meta:
        model = ExtensionOfficer

        fields = [
            "region",
            "district",
            "employer",
            "position",
            "qualification",
        ]

        widgets = {
            "region": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your region",
                }
            ),
            "district": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your district",
                }
            ),
            "employer": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Employer name",
                }
            ),
            "position": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your position",
                }
            ),
            "qualification": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["region"].required = True
        self.fields["employer"].required = True
        self.fields["position"].required = True

        self.fields["qualification"].choices = [
            ("", "Select qualification"),
            ("CERTIFICATE", "Certificate"),
            ("DIPLOMA", "Diploma"),
            ("BACHELOR", "Bachelor's Degree"),
            ("MASTERS", "Master's Degree"),
            ("PHD", "PhD"),
        ]


# ============================================================================
# FINANCIAL INSTITUTION PROFILE
# ============================================================================

class FinancialInstitutionProfileForm(forms.ModelForm):
    """
    Form for creating/updating financial institution profile.

    Phone and email are stored in User.
    """

    class Meta:
        model = FinancialInstitution

        fields = [
            "institution_name",
            "institution_type",
            "address",
            "logo",
        ]

        widgets = {
            "institution_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter institution name",
                }
            ),
            "institution_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Physical address",
                }
            ),
            "logo": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["institution_name"].required = True
        self.fields["institution_type"].required = True

        self.fields["institution_type"].choices = [
            ("", "Select institution type"),
            ("BANK", "Bank"),
            ("SACCOS", "SACCOS"),
            ("MFI", "Microfinance Institution"),
        ]


# ============================================================================
# ORDER
# ============================================================================

class OrderForm(forms.Form):
    """
    Form for creating orders.
    """

    product_id = forms.CharField(
        widget=forms.HiddenInput()
    )

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": 1,
                "placeholder": "Quantity",
            }
        ),
    )

    delivery_address = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Enter delivery address",
            }
        ),
    )


# ============================================================================
# BUYING REQUEST
# ============================================================================

class BuyingRequestForm(forms.ModelForm):
    """
    Form for creating/editing buying requests.
    """

    class Meta:
        model = BuyingRequest

        fields = [
            "crop",
            "quantity_kg",
            "price_offered",
            "location",
            "expiry_date",
        ]

        widgets = {
            "crop": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Maize, Rice, Beans",
                }
            ),
            "quantity_kg": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Quantity in kg",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "price_offered": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Price per kg in TSh",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your location / region",
                }
            ),
            "expiry_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["crop"].required = True
        self.fields["quantity_kg"].required = True
        self.fields["price_offered"].required = True
        self.fields["location"].required = True
        self.fields["expiry_date"].required = True

        if not self.instance.pk:
            self.fields["expiry_date"].initial = (
                timezone.now().date()
                + timezone.timedelta(days=30)
            )

    def clean_quantity_kg(self):
        quantity = self.cleaned_data.get("quantity_kg")

        if quantity is not None and quantity <= 0:
            raise ValidationError(
                "Quantity must be greater than zero."
            )

        return quantity

    def clean_price_offered(self):
        price = self.cleaned_data.get("price_offered")

        if price is not None and price <= 0:
            raise ValidationError(
                "Offered price must be greater than zero."
            )

        return price

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get("expiry_date")

        if expiry_date and expiry_date < timezone.now().date():
            raise ValidationError(
                "Expiry date cannot be in the past."
            )

        return expiry_date


# ============================================================================
# ADVICE
# ============================================================================

class AdviceForm(forms.ModelForm):
    """
    Form for creating/editing farming advice.
    """

    class Meta:
        model = Advice

        fields = [
            "title",
            "content",
            "category",
            "crop",
            "image",
            "is_published",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter advice title",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Write your advice content",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "crop": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Specific crop (optional)",
                }
            ),
            "image": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "is_published": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["title"].required = True
        self.fields["content"].required = True
        self.fields["category"].required = True


# ============================================================================
# LOAN PRODUCT
# ============================================================================

class LoanProductForm(forms.ModelForm):
    """
    Form for creating/editing loan products.
    """

    class Meta:
        model = LoanProduct

        fields = [
            "name",
            "loan_type",
            "interest_rate",
            "min_amount",
            "max_amount",
            "duration_months",
            "repayment_frequency",
            "grace_period_days",
            "minimum_credit_score",
            "description",
            "is_active",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter loan product name",
                }
            ),
            "loan_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "interest_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Interest rate %",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "min_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Minimum amount (TSh)",
                    "min": "0",
                }
            ),
            "max_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Maximum amount (TSh)",
                    "min": "0",
                }
            ),
            "duration_months": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Duration in months",
                    "min": "1",
                }
            ),
            "repayment_frequency": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "grace_period_days": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Grace period in days",
                }
            ),
            "minimum_credit_score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "max": 100,
                    "placeholder": "Minimum readiness score (0-100)",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Product description",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name"].required = True
        self.fields["interest_rate"].required = True
        self.fields["min_amount"].required = True
        self.fields["max_amount"].required = True
        self.fields["duration_months"].required = True

        self.fields["min_amount"].help_text = (
            "Must be less than maximum amount."
        )

        self.fields["max_amount"].help_text = (
            "Must be greater than minimum amount."
        )

    def clean_interest_rate(self):
        interest_rate = self.cleaned_data.get("interest_rate")

        if interest_rate is not None and interest_rate < 0:
            raise ValidationError(
                "Interest rate cannot be negative."
            )

        return interest_rate

    def clean_duration_months(self):
        duration = self.cleaned_data.get("duration_months")

        if duration is not None and duration <= 0:
            raise ValidationError(
                "Duration must be greater than zero."
            )

        return duration

    def clean(self):
        cleaned_data = super().clean()

        min_amount = cleaned_data.get("min_amount")
        max_amount = cleaned_data.get("max_amount")

        if min_amount is not None and max_amount is not None:
            if min_amount >= max_amount:
                raise ValidationError(
                    "Minimum amount must be less than maximum amount."
                )

        return cleaned_data


# ============================================================================
# LOAN APPLICATION
# ============================================================================

class LoanApplicationForm(forms.ModelForm):
    """
    Form for updating loan application status.
    """

    class Meta:
        model = LoanApplication

        fields = [
            "status",
            "remarks",
        ]

        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Add remarks...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["status"].choices = [
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("FARMER_ACCEPTED", "Farmer accepted"),
            ("DISBURSEMENT_PENDING", "Disbursement pending"),
            ("DISBURSED", "Disbursed"),
            ("ACTIVE", "Active"),
            ("REJECTED", "Rejected"),
        ]


# ============================================================================
# LOAN APPLICATION DECISION
# ============================================================================

class LoanApplicationDecisionForm(forms.Form):
    """
    Form for making decisions on loan applications.
    """

    decision = forms.ChoiceField(
        choices=[
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("request_info", "Request Information"),
            ("mark_reviewed", "Mark as Reviewed"),
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Add remarks...",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        decision = cleaned_data.get("decision")
        remarks = cleaned_data.get("remarks")

        # Remarks are especially useful for rejection/request-info decisions.
        if decision in ["reject", "request_info"] and not remarks:
            self.add_error(
                "remarks",
                "Please provide remarks for this decision.",
            )

        return cleaned_data


# ============================================================================
# LOAN PRODUCT FILTER
# ============================================================================

class LoanProductFilterForm(forms.Form):
    """
    Form for filtering loan products.
    """

    loan_type = forms.ChoiceField(
        choices=[
            ("", "All Types")
        ] + list(LoanProduct.LoanType.choices),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    is_active = forms.ChoiceField(
        choices=[
            ("", "All Status"),
            ("active", "Active"),
            ("inactive", "Inactive"),
        ],
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search products...",
            }
        ),
    )


# ============================================================================
# APPLICATION FILTER
# ============================================================================

class ApplicationFilterForm(forms.Form):
    """
    Form for filtering loan applications.

    NOTE:
    LoanStatus must exist in models.py or be imported from the
    module where it is defined.
    """

    status = forms.ChoiceField(
        choices=[
            ("", "All Status"),
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("FARMER_ACCEPTED", "Farmer accepted"),
            ("DISBURSEMENT_PENDING", "Disbursement pending"),
            ("DISBURSED", "Disbursed"),
            ("ACTIVE", "Active"),
            ("REJECTED", "Rejected"),
        ],
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    loan_type = forms.ChoiceField(
        choices=[
            ("", "All Types")
        ] + list(LoanProduct.LoanType.choices),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search by name, phone, ID...",
            }
        ),
    )

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise ValidationError(
                "Start date cannot be later than end date."
            )

        return cleaned_data