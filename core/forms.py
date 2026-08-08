from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import User, Product, Category, Supplier, Buyer, BuyingRequest, ExtensionOfficer, Advice


class RegisterForm(UserCreationForm):
    """Registration form - NO password restrictions"""
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )
    phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your phone number (optional)'
        })
    )
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to all fields
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs'):
                field.widget.attrs['class'] = 'form-control'
        
        # Remove password validation help text
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''
        
        # Override password fields to remove validators
        self.fields['password1'].validators = []
        self.fields['password2'].validators = []
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and User.objects.filter(phone=phone).exists():
            raise ValidationError("A user with this phone number already exists.")
        return phone
    
    def clean_password1(self):
        """Allow any password - no restrictions"""
        password1 = self.cleaned_data.get('password1')
        # Just check if it's not empty
        if not password1 or len(password1) < 1:
            raise ValidationError("Password cannot be empty.")
        return password1
    
    def clean_password2(self):
        """Check if passwords match"""
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match.")
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Login form"""
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })
    )
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            
            if user is None:
                raise ValidationError("Invalid username or password.")
            
            if not user.is_active:
                raise ValidationError("This account is inactive. Please contact support.")
            
            self.user_cache = user
        
        return self.cleaned_data


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile"""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'profile_photo']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_photo': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email


class ProductForm(forms.ModelForm):
    """Form for creating/editing products"""
    
    class Meta:
        model = Product  # ← Sasa Product imeimport
        fields = ['category', 'name', 'description', 'price', 'stock', 'unit', 'image', 'is_available']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter product name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Product description'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price in TSh'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity in stock'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., kg, piece, bag'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add required fields
        self.fields['category'].required = True
        self.fields['name'].required = True
        self.fields['price'].required = True
        self.fields['stock'].required = True
        
        
# Ongeza hii mwishoni mwa core/forms.py

class SupplierProfileForm(forms.ModelForm):
    """Form for creating supplier profile"""
    
    class Meta:
        model = Supplier
        fields = ['company_name', 'registration_number', 'phone', 'email', 'address', 'location', 'logo']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter company name'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business registration number'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Physical address'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City/Area'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_name'].required = True
        self.fields['phone'].required = True
        
        

class BuyerProfileForm(forms.ModelForm):
    """Form for creating buyer profile"""
    
    class Meta:
        model = Buyer
        fields = ['company_name', 'phone', 'email', 'location']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company name (optional)'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your location'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].required = True


class OrderForm(forms.Form):
    """Form for creating orders"""
    product_id = forms.CharField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={
        'class': 'form-control',
        'min': 1
    }))
    delivery_address = forms.CharField(widget=forms.Textarea(attrs={
        'class': 'form-control',
        'rows': 2,
        'placeholder': 'Enter delivery address'
    }), required=False)
    
class BuyingRequestForm(forms.ModelForm):
    """Form for creating/editing buying requests"""
    
    class Meta:
        model = BuyingRequest
        fields = ['crop', 'quantity_kg', 'price_offered', 'location', 'expiry_date']
        widgets = {
            'crop': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Maize, Rice, Beans'
            }),
            'quantity_kg': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Quantity in kg'
            }),
            'price_offered': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Price per kg in TSh'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your location/region'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['crop'].required = True
        self.fields['quantity_kg'].required = True
        self.fields['price_offered'].required = True
        self.fields['location'].required = True
        self.fields['expiry_date'].required = True
        
        # Set default expiry date to 30 days from now
        if not self.instance.pk:
            self.fields['expiry_date'].initial = timezone.now().date() + timezone.timedelta(days=30)
            

class ExtensionOfficerProfileForm(forms.ModelForm):
    """Form for creating extension officer profile"""
    
    class Meta:
        model = ExtensionOfficer
        fields = ['region', 'district', 'employer', 'position', 'qualification']
        widgets = {
            'region': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your region'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your district'}),
            'employer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employer name'}),
            'position': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your position'}),
            'qualification': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['region'].required = True
        self.fields['employer'].required = True
        self.fields['position'].required = True
        
        # Qualification choices
        self.fields['qualification'].choices = [
            ('', 'Select qualification'),
            ('CERTIFICATE', 'Certificate'),
            ('DIPLOMA', 'Diploma'),
            ('BACHELOR', 'Bachelor\'s Degree'),
            ('MASTERS', 'Master\'s Degree'),
            ('PHD', 'PhD'),
        ]


class AdviceForm(forms.ModelForm):
    """Form for creating/editing advice"""
    
    class Meta:
        model = Advice
        fields = ['title', 'content', 'category', 'crop', 'image', 'is_published']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter advice title'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Write your advice content'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'crop': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specific crop (optional)'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = True
        self.fields['content'].required = True
        self.fields['category'].required = True