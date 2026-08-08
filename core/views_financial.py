"""
Financial Institution Views - Loan management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import FinancialInstitution, LoanProduct, LoanApplication, Farmer
from .forms import FinancialInstitutionProfileForm, LoanProductForm


@login_required
def financial_profile_create(request):
    """Create financial institution profile"""
    if FinancialInstitution.objects.filter(user=request.user).exists():
        messages.info(request, "You already have a financial institution profile.")
        return redirect('financial_dashboard')
    
    if request.method == 'POST':
        form = FinancialInstitutionProfileForm(request.POST, request.FILES)
        if form.is_valid():
            institution = form.save(commit=False)
            institution.user = request.user
            institution.save()
            messages.success(request, "Financial institution profile created successfully!")
            return redirect('financial_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FinancialInstitutionProfileForm()
    
    return render(request, 'financial/profile_create.html', {'form': form})


@login_required
def financial_dashboard(request):
    """Financial Institution dashboard"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    # Get loan products
    loan_products = LoanProduct.objects.filter(institution=institution).count()
    
    # Get loan applications
    applications = LoanApplication.objects.filter(loan_product__institution=institution)
    total_applications = applications.count()
    pending_applications = applications.filter(status='PENDING').count()
    approved_applications = applications.filter(status='APPROVED').count()
    disbursed_applications = applications.filter(status='DISBURSED').count()
    rejected_applications = applications.filter(status='REJECTED').count()
    recent_applications = applications.order_by('-created_at')[:5]
    
    context = {
        'institution': institution,
        'loan_products': loan_products,
        'total_applications': total_applications,
        'pending_applications': pending_applications,
        'approved_applications': approved_applications,
        'disbursed_applications': disbursed_applications,
        'rejected_applications': rejected_applications,
        'recent_applications': recent_applications,
    }
    return render(request, 'dashboards/financial.html', context)


@login_required
def financial_loan_products(request):
    """List all loan products"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    products = LoanProduct.objects.filter(institution=institution).order_by('-created_at')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)
    
    context = {
        'institution': institution,
        'products': products,
        'search': search,
    }
    return render(request, 'financial/loan_products.html', context)


@login_required
def financial_loan_product_create(request):
    """Create a new loan product"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    if request.method == 'POST':
        form = LoanProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.institution = institution
            product.save()
            messages.success(request, f"Loan product '{product.name}' created successfully!")
            return redirect('financial_loan_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoanProductForm()
    
    context = {
        'institution': institution,
        'form': form,
        'action': 'Create',
    }
    return render(request, 'financial/loan_product_form.html', context)


@login_required
def financial_loan_product_edit(request, product_id):
    """Edit a loan product"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    product = get_object_or_404(LoanProduct, id=product_id, institution=institution)
    
    if request.method == 'POST':
        form = LoanProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Loan product '{product.name}' updated successfully!")
            return redirect('financial_loan_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoanProductForm(instance=product)
    
    context = {
        'institution': institution,
        'form': form,
        'action': 'Edit',
        'product': product,
    }
    return render(request, 'financial/loan_product_form.html', context)


@login_required
def financial_loan_product_delete(request, product_id):
    """Delete a loan product"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    product = get_object_or_404(LoanProduct, id=product_id, institution=institution)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f"Loan product '{product_name}' deleted successfully!")
        return redirect('financial_loan_products')
    
    context = {
        'institution': institution,
        'product': product,
    }
    return render(request, 'financial/loan_product_confirm_delete.html', context)


@login_required
def financial_applications(request):
    """View all loan applications"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    applications = LoanApplication.objects.filter(loan_product__institution=institution).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        applications = applications.filter(status=status)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        applications = applications.filter(
            Q(farmer__full_name__icontains=search) |
            Q(loan_product__name__icontains=search)
        )
    
    paginator = Paginator(applications, 10)
    page_number = request.GET.get('page')
    applications = paginator.get_page(page_number)
    
    # Status counts
    all_applications = LoanApplication.objects.filter(loan_product__institution=institution)
    status_counts = {
        'PENDING': all_applications.filter(status='PENDING').count(),
        'APPROVED': all_applications.filter(status='APPROVED').count(),
        'DISBURSED': all_applications.filter(status='DISBURSED').count(),
        'REJECTED': all_applications.filter(status='REJECTED').count(),
    }
    
    context = {
        'institution': institution,
        'applications': applications,
        'status': status,
        'status_counts': status_counts,
        'search': search,
    }
    return render(request, 'financial/applications.html', context)


@login_required
def financial_application_detail(request, application_id):
    """View loan application details"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    application = get_object_or_404(
        LoanApplication, 
        id=application_id, 
        loan_product__institution=institution
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            application.status = 'APPROVED'
            application.approved_date = timezone.now()
            application.save()
            messages.success(request, "Loan application approved successfully!")
            return redirect('financial_application_detail', application_id=application.id)
            
        elif action == 'disburse':
            application.status = 'DISBURSED'
            application.save()
            messages.success(request, "Loan disbursed successfully!")
            return redirect('financial_application_detail', application_id=application.id)
            
        elif action == 'reject':
            application.status = 'REJECTED'
            application.remarks = request.POST.get('remarks', '')
            application.save()
            messages.success(request, "Loan application rejected!")
            return redirect('financial_applications')
    
    context = {
        'institution': institution,
        'application': application,
    }
    return render(request, 'financial/application_detail.html', context)