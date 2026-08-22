from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from .forms import RegisterForm, LoginForm
from .models import (
    User, Farmer, Supplier, Buyer, Order, Product, 
    LoanApplication, Advice, BuyingRequest, InterestedFarmer,
    LoanProduct, ExtensionOfficer, FinancialInstitution
)


def index_view(request):
    """Landing page"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'index.html')


def register_view(request):
    """Register new user"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Account created! Welcome {user.username}")
            return redirect('login')
        else:
            messages.error(request, "Please correct the errors below")
    else:
        form = RegisterForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    """Login user - redirect based on role"""
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")

                if user.role == 'ADMIN' or user.is_staff or user.is_superuser:
                    if user.role == 'ADMIN' and (not user.is_staff or not user.is_superuser):
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=['is_staff', 'is_superuser'])
                    return redirect('admin:index')

                return redirect(get_dashboard_url(user))
        messages.error(request, "Invalid username or password")
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    """Logout user"""
    logout(request)
    messages.info(request, "You have been logged out")
    return redirect('index')


def get_dashboard_url(user):
    """Get the appropriate dashboard URL based on user role"""
    role = user.role
    
    if role == 'ADMIN' or user.is_staff or user.is_superuser:
        return 'admin:index'
    elif role == 'SUPPLIER':
        if Supplier.objects.filter(user=user).exists():
            return 'supplier_dashboard'
        else:
            return 'supplier_profile_create'
    elif role == 'BUYER':
        if Buyer.objects.filter(user=user).exists():
            return 'buyer_dashboard'
        else:
            return 'buyer_profile_create'
    elif role == 'FINANCIAL':
        if FinancialInstitution.objects.filter(user=user).exists():
            return 'financial_dashboard'
        else:
            return 'financial_profile_create'
    elif role == 'EXTENSION_OFFICER':
        if ExtensionOfficer.objects.filter(user=user).exists():
            return 'extension_dashboard'
        else:
            return 'extension_profile_create'
    else:
        return 'dashboard'


@login_required
def dashboard_view(request):
    """Dashboard - redirect to role-specific dashboard"""
    user = request.user
    return redirect(get_dashboard_url(user))


# ===================== DASHBOARD DATA FUNCTIONS =====================

def get_super_admin_dashboard_data():
    """Data for Super Admin dashboard"""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # Users by role
    suppliers = User.objects.filter(role='SUPPLIER').count()
    buyers = User.objects.filter(role='BUYER').count()
    financial = User.objects.filter(role='FINANCIAL').count()
    extension = User.objects.filter(role='EXTENSION_OFFICER').count()
    
    # Farmers
    total_farmers = Farmer.objects.count()
    active_farmers = Farmer.objects.filter(is_active=True).count()
    
    # Orders
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='PENDING').count()
    
    # Recent users (last 5)
    recent_users = User.objects.all().order_by('-created_at')[:5]
    
    return {
        'total_users': total_users,
        'active_users': active_users,
        'suppliers': suppliers,
        'buyers': buyers,
        'financial': financial,
        'extension': extension,
        'total_farmers': total_farmers,
        'active_farmers': active_farmers,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'recent_users': recent_users,
    }


def get_supplier_dashboard_data(user):
    """Data for Supplier dashboard"""
    supplier = Supplier.objects.filter(user=user).first()
    
    if not supplier:
        return {
            'supplier': None,
            'total_products': 0,
            'active_products': 0,
            'total_orders': 0,
            'pending_orders': 0,
            'accepted_orders': 0,
            'delivered_orders': 0,
            'recent_orders': [],
            'location_summary': 'Not set',
        }
    
    # Products
    total_products = Product.objects.filter(supplier=supplier).count()
    active_products = Product.objects.filter(supplier=supplier, is_available=True).count()
    
    # Orders
    orders = Order.objects.filter(supplier=supplier)
    total_orders = orders.count()
    pending_orders = orders.filter(status='PENDING').count()
    accepted_orders = orders.filter(status='ACCEPTED').count()
    delivered_orders = orders.filter(status='DELIVERED').count()
    
    # Recent orders
    recent_orders = orders.order_by('-created_at')[:5]
    
    # Get location summary
    location_parts = []
    if supplier.village:
        location_parts.append(supplier.village)
    if supplier.ward:
        location_parts.append(supplier.ward)
    if supplier.district:
        location_parts.append(supplier.district)
    if supplier.region:
        location_parts.append(supplier.region)
    
    location_summary = ", ".join(location_parts) if location_parts else "Not set"
    
    return {
        'supplier': supplier,
        'total_products': total_products,
        'active_products': active_products,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'accepted_orders': accepted_orders,
        'delivered_orders': delivered_orders,
        'recent_orders': recent_orders,
        'location_summary': location_summary,
    }
    

def get_buyer_dashboard_data(user):
    """Data for Buyer dashboard"""
    buyer = Buyer.objects.filter(user=user).first()
    
    if not buyer:
        return {
            'buyer': None,
            'total_requests': 0,
            'open_requests': 0,
            'closed_requests': 0,
            'recent_requests': [],
            'interested_farmers': [],
            'interested_farmers_count': 0,
        }
    
    requests = BuyingRequest.objects.filter(buyer=buyer).order_by('-created_at')
    total_requests = requests.count()
    open_requests = requests.filter(is_open=True).count()
    closed_requests = requests.filter(is_open=False).count()
    recent_requests = requests[:5]
    
    interested_farmers = []
    interested_farmers_count = 0
    
    all_interested = InterestedFarmer.objects.filter(
        buying_request__buyer=buyer
    ).select_related('farmer', 'buying_request').order_by('-created_at')
    
    if all_interested.exists():
        grouped = {}
        for item in all_interested:
            req_id = item.buying_request.id
            if req_id not in grouped:
                grouped[req_id] = {
                    'request': item.buying_request,
                    'farmers': []
                }
            grouped[req_id]['farmers'].append(item)
            interested_farmers_count += 1
        
        interested_farmers = list(grouped.values())
    
    return {
        'buyer': buyer,
        'total_requests': total_requests,
        'open_requests': open_requests,
        'closed_requests': closed_requests,
        'recent_requests': recent_requests,
        'interested_farmers': interested_farmers,
        'interested_farmers_count': interested_farmers_count,
    }


def get_financial_dashboard_data(user):
    """Data for Financial Institution dashboard"""
    institution = FinancialInstitution.objects.filter(user=user).first()
    
    if not institution:
        return {
            'institution': None,
            'loan_products': 0,
            'total_applications': 0,
            'pending_applications': 0,
            'approved_applications': 0,
            'disbursed_applications': 0,
            'rejected_applications': 0,
            'recent_applications': [],
        }
    
    loan_products = LoanProduct.objects.filter(institution=institution).count()
    applications = LoanApplication.objects.filter(loan_product__institution=institution)
    
    return {
        'institution': institution,
        'loan_products': loan_products,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(status='PENDING').count(),
        'approved_applications': applications.filter(status='APPROVED').count(),
        'disbursed_applications': applications.filter(status='DISBURSED').count(),
        'rejected_applications': applications.filter(status='REJECTED').count(),
        'recent_applications': applications.order_by('-created_at')[:5],
    }


def get_extension_dashboard_data(user):
    """Data for Extension Officer dashboard"""
    officer = ExtensionOfficer.objects.filter(user=user).first()
    
    if not officer:
        return {
            'officer': None,
            'total_advice': 0,
            'published_advice': 0,
            'total_farmers': 0,
            'active_farmers': 0,
            'recent_advice': [],
        }
    
    advice = Advice.objects.filter(author=officer)
    total_advice = advice.count()
    published_advice = advice.filter(is_published=True).count()
    recent_advice = advice.order_by('-created_at')[:5]
    
    if officer.region:
        farmers = Farmer.objects.filter(region__icontains=officer.region)
        total_farmers = farmers.count()
        active_farmers = farmers.filter(is_active=True).count()
    else:
        total_farmers = Farmer.objects.count()
        active_farmers = Farmer.objects.filter(is_active=True).count()
    
    return {
        'officer': officer,
        'total_advice': total_advice,
        'published_advice': published_advice,
        'total_farmers': total_farmers,
        'active_farmers': active_farmers,
        'recent_advice': recent_advice,
    }


@login_required
def profile_view(request):
    """View and update profile with company/institution info"""
    user = request.user
    
    # Get role-specific profile
    supplier_profile = None
    buyer_profile = None
    extension_profile = None
    financial_profile = None
    
    if user.role == 'SUPPLIER':
        supplier_profile = Supplier.objects.filter(user=user).first()
    elif user.role == 'BUYER':
        buyer_profile = Buyer.objects.filter(user=user).first()
    elif user.role == 'EXTENSION_OFFICER':
        extension_profile = ExtensionOfficer.objects.filter(user=user).first()
    elif user.role == 'FINANCIAL':
        financial_profile = FinancialInstitution.objects.filter(user=user).first()
    
    if request.method == 'POST':
        # Update user info
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.address = request.POST.get('address', user.address)
        
        if request.FILES.get('profile_photo'):
            user.profile_photo = request.FILES.get('profile_photo')
        
        user.save()
        
        # Update role-specific profile
        if user.role == 'SUPPLIER' and supplier_profile:
            supplier_profile.company_name = request.POST.get('company_name', supplier_profile.company_name)
            supplier_profile.registration_number = request.POST.get('registration_number', supplier_profile.registration_number)
            supplier_profile.address = request.POST.get('company_address', supplier_profile.address)
            supplier_profile.region = request.POST.get('region', supplier_profile.region)
            supplier_profile.district = request.POST.get('district', supplier_profile.district)
            supplier_profile.ward = request.POST.get('ward', supplier_profile.ward)
            supplier_profile.village = request.POST.get('village', supplier_profile.village)
            supplier_profile.phone = request.POST.get('company_phone', supplier_profile.phone)
            supplier_profile.email = request.POST.get('company_email', supplier_profile.email)
            if request.FILES.get('logo'):
                supplier_profile.logo = request.FILES.get('logo')
            supplier_profile.save()
            
        elif user.role == 'FINANCIAL' and financial_profile:
            financial_profile.institution_name = request.POST.get('institution_name', financial_profile.institution_name)
            financial_profile.institution_type = request.POST.get('institution_type', financial_profile.institution_type)
            financial_profile.address = request.POST.get('company_address', financial_profile.address)
            financial_profile.phone = request.POST.get('company_phone', financial_profile.phone)
            financial_profile.email = request.POST.get('company_email', financial_profile.email)
            if request.FILES.get('logo'):
                financial_profile.logo = request.FILES.get('logo')
            financial_profile.save()
            
        elif user.role == 'BUYER' and buyer_profile:
            buyer_profile.company_name = request.POST.get('company_name', buyer_profile.company_name)
            buyer_profile.location = request.POST.get('location', buyer_profile.location)
            buyer_profile.phone = request.POST.get('company_phone', buyer_profile.phone)
            buyer_profile.email = request.POST.get('company_email', buyer_profile.email)
            buyer_profile.save()
            
        elif user.role == 'EXTENSION_OFFICER' and extension_profile:
            extension_profile.region = request.POST.get('region', extension_profile.region)
            extension_profile.district = request.POST.get('district', extension_profile.district)
            extension_profile.employer = request.POST.get('employer', extension_profile.employer)
            extension_profile.position = request.POST.get('position', extension_profile.position)
            extension_profile.qualification = request.POST.get('qualification', extension_profile.qualification)
            extension_profile.save()
        
        messages.success(request, "Profile updated successfully!")
        return redirect('profile')
    
    context = {
        'user': user,
        'supplier_profile': supplier_profile,
        'buyer_profile': buyer_profile,
        'extension_profile': extension_profile,
        'financial_profile': financial_profile,
    }
    return render(request, 'profile.html', context)