# core/views_financial.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json

from .models import (
    FinancialInstitution, LoanProduct, LoanApplication, Farmer,
    Order, BuyingRequest, InterestedFarmer, Loan, LoanDecisionAudit,
    LoanStatus, OrderStatus, PaymentStatus, UserRole, Repayment, 
    RepaymentStatus, PaymentTransaction, PaymentTransactionStatus,
    LoanDisbursement
)
from .forms import (
    FinancialInstitutionProfileForm, LoanProductForm,
    LoanApplicationDecisionForm
)
from .services.notification_service import send_event_sms
from .services.disbursement_service import request_disbursement
from .services.repayment_service import generate_repayment_schedule

import logging
logger = logging.getLogger(__name__)

# ============================================================
# DECORATORS
# ============================================================

financial_required = user_passes_test(
    lambda user: user.is_authenticated and user.role == UserRole.FINANCIAL,
    login_url='login',
)


# ============================================================
# DASHBOARD
# ============================================================

@financial_required
def financial_dashboard(request):
    """Financial Institution dashboard with full metrics"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    # Get all applications for this institution
    applications = LoanApplication.objects.filter(
        loan_product__institution=institution
    ).select_related('farmer', 'loan_product')
    
    # Status counts
    pending = applications.filter(status='PENDING')
    under_review = applications.filter(status='UNDER_REVIEW')
    info_required = applications.filter(status='INFO_REQUIRED')
    approved = applications.filter(status='APPROVED')
    farmer_accepted = applications.filter(status='FARMER_ACCEPTED')
    disbursement_pending = applications.filter(status='DISBURSEMENT_PENDING')
    disbursed = applications.filter(status__in=[
        LoanStatus.DISBURSED, LoanStatus.ACTIVE, 
        LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE
    ])
    rejected = applications.filter(status='REJECTED')
    farmer_declined = applications.filter(status='FARMER_DECLINED')
    repaid = applications.filter(status__in=[LoanStatus.FULLY_REPAID, LoanStatus.REPAID])
    defaulted = applications.filter(status='DEFAULTED')
    
    # Active loans
    active_loans = Loan.objects.filter(
        application__loan_product__institution=institution,
        status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, 
                   LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE],
    )
    
    # Overdue repayments
    overdue_repayments = Repayment.objects.filter(
        loan__application__loan_product__institution=institution,
        status=RepaymentStatus.OVERDUE,
    )
    
    # Financial metrics
    total_disbursed = disbursed.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_recovered = Repayment.objects.filter(
        loan__application__loan_product__institution=institution
    ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    total_outstanding = active_loans.aggregate(total=Sum('outstanding_balance'))['total'] or Decimal('0')
    
    repayment_rate = int((total_recovered / total_disbursed * 100)) if total_disbursed > 0 else 0
    
    # Active farmers
    active_farmers = Farmer.objects.filter(
        loan_applications__loan_product__institution=institution
    ).distinct().count()
    
    # Recent activities
    pending_list = pending.order_by('-created_at')[:5]
    recent_applications = applications.order_by('-created_at')[:5]
    recent_disbursements = LoanDisbursement.objects.filter(
        application__loan_product__institution=institution
    ).order_by('-requested_at')[:5]
    
    # Loan products count
    loan_products_count = LoanProduct.objects.filter(
        institution=institution, is_active=True
    ).count()
    
    # Monthly trends
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_stats = applications.filter(
        created_at__gte=six_months_ago
    ).extra(
        select={'month': "strftime('%%m', created_at)"}
    ).values('month').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    ).order_by('month')
    
    context = {
        'institution': institution,
        
        # Application stats
        'pending_applications': pending.count(),
        'pending_applications_list': pending_list,
        'under_review_applications': under_review.count(),
        'info_required_applications': info_required.count(),
        'approved_applications': approved.count(),
        'farmer_accepted_applications': farmer_accepted.count(),
        'disbursement_pending_applications': disbursement_pending.count(),
        'disbursed_applications': disbursed.count(),
        'rejected_applications': rejected.count(),
        'farmer_declined_applications': farmer_declined.count(),
        'repaid_applications': repaid.count(),
        'defaulted_applications': defaulted.count(),
        
        # Loan stats
        'active_loans': active_loans.count(),
        'overdue_repayments': overdue_repayments.count(),
        'total_outstanding': total_outstanding,
        
        # Financial metrics
        'total_disbursed': total_disbursed,
        'total_recovered': total_recovered,
        'repayment_rate': repayment_rate,
        'active_farmers': active_farmers,
        
        # Products
        'loan_products': loan_products_count,
        'total_applications': applications.count(),
        
        # Recent activities
        'recent_applications': recent_applications,
        'recent_disbursements': recent_disbursements,
        
        # Monthly trends
        'monthly_stats': monthly_stats,
    }
    
    return render(request, 'dashboards/financial.html', context)


# ============================================================
# LOAN APPLICATIONS
# ============================================================

@financial_required
def financial_applications(request):
    """List all loan applications with filtering"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    # Get base queryset
    applications_qs = LoanApplication.objects.filter(
        loan_product__institution=institution
    ).select_related('farmer', 'loan_product').order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        applications_qs = applications_qs.filter(status=status)
    
    # Filter by loan type
    loan_type = request.GET.get('loan_type', '')
    if loan_type:
        applications_qs = applications_qs.filter(loan_product__loan_type=loan_type)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        applications_qs = applications_qs.filter(
            Q(farmer__full_name__icontains=search) |
            Q(farmer__phone_number__icontains=search) |
            Q(loan_product__name__icontains=search) |
            Q(id__icontains=search)
        )
    
    # Date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        applications_qs = applications_qs.filter(created_at__date__gte=date_from)
    if date_to:
        applications_qs = applications_qs.filter(created_at__date__lte=date_to)
    
    # Status counts - BEFORE pagination
    status_counts = {
        'PENDING': applications_qs.filter(status='PENDING').count(),
        'UNDER_REVIEW': applications_qs.filter(status='UNDER_REVIEW').count(),
        'INFO_REQUIRED': applications_qs.filter(status='INFO_REQUIRED').count(),
        'APPROVED': applications_qs.filter(status='APPROVED').count(),
        'FARMER_ACCEPTED': applications_qs.filter(status='FARMER_ACCEPTED').count(),
        'DISBURSEMENT_PENDING': applications_qs.filter(status='DISBURSEMENT_PENDING').count(),
        'DISBURSED': applications_qs.filter(status='DISBURSED').count(),
        'REJECTED': applications_qs.filter(status='REJECTED').count(),
        'FARMER_DECLINED': applications_qs.filter(status='FARMER_DECLINED').count(),
        'REPAID': applications_qs.filter(status='REPAID').count(),
        'DEFAULTED': applications_qs.filter(status='DEFAULTED').count(),
    }
    
    # Loan type counts
    loan_type_counts = {
        'INPUT': applications_qs.filter(loan_product__loan_type='INPUT').count(),
        'PRODUCTION': applications_qs.filter(loan_product__loan_type='PRODUCTION').count(),
        'MARKET': applications_qs.filter(loan_product__loan_type='MARKET').count(),
        'GENERAL': applications_qs.filter(loan_product__loan_type='GENERAL').count(),
    }
    
    # Pagination
    paginator = Paginator(applications_qs, 20)
    page_number = request.GET.get('page')
    applications = paginator.get_page(page_number)
    
    context = {
        'institution': institution,
        'applications': applications,
        'status': status,
        'loan_type': loan_type,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'status_counts': status_counts,
        'loan_type_counts': loan_type_counts,
    }
    return render(request, 'financial/applications.html', context)


@financial_required
def financial_application_detail(request, application_id):
    """View loan application with full farmer credit profile"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    application = get_object_or_404(
        LoanApplication,
        id=application_id,
        loan_product__institution=institution
    )
    
    farmer = application.farmer
    farmer.calculate_credit_readiness()
    
    # Get farmer's activity
    orders = Order.objects.filter(farmer=farmer)
    market_activities = InterestedFarmer.objects.filter(farmer=farmer)
    loan_history = LoanApplication.objects.filter(farmer=farmer)
    
    # Get related loan if exists
    loan = getattr(application, 'loan', None)
    repayments = loan.repayments.all() if loan else []
    disbursement = getattr(application, 'disbursement', None)
    
    # Get decision audit
    audits = LoanDecisionAudit.objects.filter(application=application).order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '')
        
        # ============================================================
        # APPROVE
        # ============================================================
        if action == 'approve' and application.status in [
            LoanStatus.PENDING, LoanStatus.UNDER_REVIEW, LoanStatus.INFO_REQUIRED
        ]:
            with transaction.atomic():
                application.status = LoanStatus.APPROVED
                application.approved_date = timezone.now()
                application.reviewed_by = request.user
                application.decision_at = timezone.now()
                application.decision_notes = remarks
                application.save(update_fields=[
                    'status', 'approved_date', 'reviewed_by', 
                    'decision_at', 'decision_notes', 'updated_at'
                ])
                
                LoanDecisionAudit.objects.create(
                    application=application,
                    staff=request.user,
                    decision='APPROVED',
                    notes=remarks
                )
                
                # Send SMS to farmer
                transaction.on_commit(lambda: send_event_sms(
                    f'loan-approved-{application.id}',
                    application.farmer.phone_number,
                    f'Lunyili AgroSmart: Ombi lako limeidhinishwa kwa TSh {int(application.amount):,}. Piga *566# > 7 kusoma masharti na kukubali au kukataa.'
                ))
                
            messages.success(request, f"Loan #{application.id} approved successfully!")
            return redirect('financial_application_detail', application_id=application.id)
        
        # ============================================================
        # REQUEST MORE INFO
        # ============================================================
        elif action == 'request_info' and application.status in [
            LoanStatus.PENDING, LoanStatus.UNDER_REVIEW
        ]:
            with transaction.atomic():
                application.status = LoanStatus.INFO_REQUIRED
                application.reviewed_by = request.user
                application.decision_at = timezone.now()
                application.decision_notes = remarks
                application.save(update_fields=[
                    'status', 'reviewed_by', 'decision_at', 
                    'decision_notes', 'updated_at'
                ])
                
                LoanDecisionAudit.objects.create(
                    application=application,
                    staff=request.user,
                    decision='INFO_REQUIRED',
                    notes=remarks
                )
                
                # Send SMS to farmer
                transaction.on_commit(lambda: send_event_sms(
                    f'loan-info-required-{application.id}',
                    application.farmer.phone_number,
                    f'Lunyili AgroSmart: Ombi lako linahitaji taarifa za ziada. Piga *566# > 5 kukamilisha.'
                ))
                
            messages.success(request, f"Additional information requested for #{application.id}.")
            return redirect('financial_application_detail', application_id=application.id)
        
        # ============================================================
        # REJECT
        # ============================================================
        elif action == 'reject' and application.status in [
            LoanStatus.PENDING, LoanStatus.UNDER_REVIEW, LoanStatus.INFO_REQUIRED
        ]:
            with transaction.atomic():
                application.status = LoanStatus.REJECTED
                application.reviewed_by = request.user
                application.decision_at = timezone.now()
                application.decision_notes = remarks
                application.save(update_fields=[
                    'status', 'reviewed_by', 'decision_at', 
                    'decision_notes', 'updated_at'
                ])
                
                LoanDecisionAudit.objects.create(
                    application=application,
                    staff=request.user,
                    decision='REJECTED',
                    notes=remarks
                )
                
                # Send SMS to farmer
                transaction.on_commit(lambda: send_event_sms(
                    f'loan-rejected-{application.id}',
                    application.farmer.phone_number,
                    f'Lunyili AgroSmart: Ombi lako la mkopo halijakubaliwa. Sababu: {remarks[:100]}. Piga *566# kwa maelezo zaidi.'
                ))
                
            messages.success(request, f"Loan #{application.id} rejected.")
            return redirect('financial_applications')
        
        # ============================================================
        # DISBURSE (Legacy - now farmer must accept first)
        # ============================================================
        elif action == 'disburse' and application.status == LoanStatus.APPROVED:
            # This should now be handled by farmer acceptance
            # But we can send a reminder
            transaction.on_commit(lambda: send_event_sms(
                f'loan-disburse-reminder-{application.id}',
                application.farmer.phone_number,
                f'Lunyili AgroSmart: Mkopo wako wa TSh {int(application.amount):,} umeidhinishwa. Piga *566# > 7 kukubali masharti.'
            ))
            messages.info(request, f"Loan #{application.id} is approved. Farmer must accept before disbursement.")
            return redirect('financial_application_detail', application_id=application.id)
        
        # ============================================================
        # MARK AS REVIEWED
        # ============================================================
        elif action == 'mark_reviewed' and application.status == LoanStatus.UNDER_REVIEW:
            with transaction.atomic():
                application.status = LoanStatus.PENDING
                application.reviewed_by = request.user
                application.decision_at = timezone.now()
                application.decision_notes = remarks
                application.save(update_fields=[
                    'status', 'reviewed_by', 'decision_at', 
                    'decision_notes', 'updated_at'
                ])
                
            messages.success(request, f"Loan #{application.id} marked as reviewed.")
            return redirect('financial_application_detail', application_id=application.id)
    
    context = {
        'institution': institution,
        'application': application,
        'farmer': farmer,
        'eligibility': farmer.get_eligibility_level(),
        'orders': orders[:10],
        'total_orders': orders.count(),
        'total_order_value': orders.aggregate(total=Sum('total_amount'))['total'] or 0,
        'market_activities': market_activities[:10],
        'total_market_activities': market_activities.count(),
        'loan_history': loan_history,
        'loan': loan,
        'repayments': repayments,
        'disbursement': disbursement,
        'audits': audits,
    }
    
    return render(request, 'financial/application_detail.html', context)


# ============================================================
# LOAN PRODUCTS
# ============================================================

@financial_required
def financial_loan_products(request):
    """List loan products with management options"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    products_qs = LoanProduct.objects.filter(institution=institution).order_by('-created_at')
    
    # Filter by loan type
    loan_type = request.GET.get('loan_type', '')
    if loan_type:
        products_qs = products_qs.filter(loan_type=loan_type)
    
    # Filter by active status
    is_active = request.GET.get('is_active', '')
    if is_active == 'active':
        products_qs = products_qs.filter(is_active=True)
    elif is_active == 'inactive':
        products_qs = products_qs.filter(is_active=False)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        products_qs = products_qs.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(products_qs, 10)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)
    
    # Get statistics for each product
    for product in products:
        product.applications_count = LoanApplication.objects.filter(
            loan_product=product
        ).count()
        product.approved_count = LoanApplication.objects.filter(
            loan_product=product, status='APPROVED'
        ).count()
        product.disbursed_count = LoanApplication.objects.filter(
            loan_product=product, status='DISBURSED'
        ).count()
        product.total_disbursed = LoanApplication.objects.filter(
            loan_product=product, status='DISBURSED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    context = {
        'institution': institution,
        'products': products,
        'loan_type': loan_type,
        'is_active': is_active,
        'search': search,
    }
    return render(request, 'financial/loan_products.html', context)


@financial_required
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


@financial_required
def financial_loan_product_edit(request, product_id):
    """Edit an existing loan product"""
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


@financial_required
def financial_loan_product_detail(request, product_id):
    """View detailed information about a loan product"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    product = get_object_or_404(LoanProduct, id=product_id, institution=institution)
    
    # Get applications for this product
    applications = LoanApplication.objects.filter(loan_product=product)
    
    # Statistics
    total_applications = applications.count()
    approved = applications.filter(status='APPROVED').count()
    disbursed = applications.filter(status='DISBURSED').count()
    rejected = applications.filter(status='REJECTED').count()
    repaid = applications.filter(status='REPAID').count()
    defaulted = applications.filter(status='DEFAULTED').count()
    
    total_disbursed = applications.filter(
        status='DISBURSED'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    total_recovered = Repayment.objects.filter(
        loan__application__loan_product=product
    ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    
    # Recent applications
    recent_applications = applications.order_by('-created_at')[:10]
    
    # Performance metrics
    approval_rate = int((approved / total_applications * 100)) if total_applications > 0 else 0
    default_rate = int((defaulted / total_applications * 100)) if total_applications > 0 else 0
    repayment_rate = int((total_recovered / total_disbursed * 100)) if total_disbursed > 0 else 0
    
    context = {
        'institution': institution,
        'product': product,
        'total_applications': total_applications,
        'approved': approved,
        'disbursed': disbursed,
        'rejected': rejected,
        'repaid': repaid,
        'defaulted': defaulted,
        'total_disbursed': total_disbursed,
        'total_recovered': total_recovered,
        'approval_rate': approval_rate,
        'default_rate': default_rate,
        'repayment_rate': repayment_rate,
        'recent_applications': recent_applications,
    }
    return render(request, 'financial/loan_product_detail.html', context)


@financial_required
def financial_loan_product_toggle(request, product_id):
    """Toggle loan product active status"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    product = get_object_or_404(LoanProduct, id=product_id, institution=institution)
    
    if request.method == 'POST':
        product.is_active = not product.is_active
        product.save(update_fields=['is_active', 'updated_at'])
        status = "activated" if product.is_active else "deactivated"
        messages.success(request, f"Loan product '{product.name}' {status} successfully!")
    
    return redirect('financial_loan_products')


@financial_required
def financial_loan_product_delete(request, product_id):
    """Delete a loan product (soft delete)"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    product = get_object_or_404(LoanProduct, id=product_id, institution=institution)
    
    # Check if there are active applications
    active_applications = LoanApplication.objects.filter(
        loan_product=product,
        status__in=['PENDING', 'UNDER_REVIEW', 'INFO_REQUIRED', 'APPROVED', 'FARMER_ACCEPTED']
    ).exists()
    
    if active_applications:
        messages.error(request, f"Cannot delete '{product.name}' because it has active loan applications.")
        return redirect('financial_loan_products')
    
    if request.method == 'POST':
        product_name = product.name
        product.is_active = False
        product.is_deleted = True
        product.deleted_at = timezone.now()
        product.save(update_fields=['is_active', 'is_deleted', 'deleted_at', 'updated_at'])
        messages.success(request, f"Loan product '{product_name}' deleted successfully!")
        return redirect('financial_loan_products')
    
    context = {
        'institution': institution,
        'product': product,
    }
    return render(request, 'financial/loan_product_confirm_delete.html', context)


# ============================================================
# LOAN MONITORING
# ============================================================

@financial_required
def financial_active_loans(request):
    """View all active loans"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    loans_qs = Loan.objects.filter(
        application__loan_product__institution=institution,
        status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, 
                   LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE]
    ).select_related('application__farmer', 'application__loan_product')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        loans_qs = loans_qs.filter(status=status)
    
    # Filter by overdue
    is_overdue = request.GET.get('is_overdue', '')
    if is_overdue == 'yes':
        loans_qs = loans_qs.filter(status=LoanStatus.OVERDUE)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        loans_qs = loans_qs.filter(
            Q(application__farmer__full_name__icontains=search) |
            Q(application__farmer__phone_number__icontains=search) |
            Q(application__loan_product__name__icontains=search)
        )
    
    # Totals - BEFORE pagination
    total_outstanding = loans_qs.aggregate(total=Sum('outstanding_balance'))['total'] or Decimal('0')
    total_principal = loans_qs.aggregate(total=Sum('principal_amount'))['total'] or Decimal('0')
    total_interest = loans_qs.aggregate(total=Sum('interest_amount'))['total'] or Decimal('0')
    active_loans_count = loans_qs.count()
    
    # Pagination
    paginator = Paginator(loans_qs, 20)
    page_number = request.GET.get('page')
    loans = paginator.get_page(page_number)
    
    context = {
        'institution': institution,
        'loans': loans,
        'status': status,
        'search': search,
        'total_outstanding': total_outstanding,
        'total_principal': total_principal,
        'total_interest': total_interest,
        'active_loans_count': active_loans_count,
    }
    return render(request, 'financial/active_loans.html', context)


@financial_required
def financial_loan_detail(request, loan_id):
    """View detailed loan information"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    loan = get_object_or_404(
        Loan,
        id=loan_id,
        application__loan_product__institution=institution
    )
    
    application = loan.application
    farmer = application.farmer
    
    # Get repayments
    repayments = loan.repayments.order_by('installment_number')
    
    # Get payment transactions
    payments = PaymentTransaction.objects.filter(loan=loan).order_by('-created_at')
    
    # Get disbursement
    disbursement = getattr(application, 'disbursement', None)
    
    # Statistics
    total_paid = repayments.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    total_due = repayments.aggregate(total=Sum('total_due'))['total'] or Decimal('0')
    remaining = loan.outstanding_balance
    progress = int((total_paid / (total_due + loan.interest_amount) * 100)) if (total_due + loan.interest_amount) > 0 else 0
    
    # Overdue count
    overdue_count = repayments.filter(status=RepaymentStatus.OVERDUE).count()
    
    context = {
        'institution': institution,
        'loan': loan,
        'application': application,
        'farmer': farmer,
        'repayments': repayments,
        'payments': payments,
        'disbursement': disbursement,
        'total_paid': total_paid,
        'total_due': total_due,
        'remaining': remaining,
        'progress': progress,
        'overdue_count': overdue_count,
    }
    return render(request, 'financial/loan_detail.html', context)


# ============================================================
# REPAYMENTS
# ============================================================

@financial_required
def financial_repayments(request):
    """View all repayments"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    repayments_qs = Repayment.objects.filter(
        loan__application__loan_product__institution=institution
    ).select_related('loan__application__farmer', 'loan__application__loan_product')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        repayments_qs = repayments_qs.filter(status=status)
    
    # Filter by due date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        repayments_qs = repayments_qs.filter(due_date__gte=date_from)
    if date_to:
        repayments_qs = repayments_qs.filter(due_date__lte=date_to)
    
    # Search by farmer
    search = request.GET.get('search', '')
    if search:
        repayments_qs = repayments_qs.filter(
            Q(loan__application__farmer__full_name__icontains=search) |
            Q(loan__application__farmer__phone_number__icontains=search)
        )
    
    # Order by due date (show overdue first)
    repayments_qs = repayments_qs.order_by('status', 'due_date')
    
    # Summary - BEFORE pagination
    total_due = repayments_qs.aggregate(total=Sum('total_due'))['total'] or Decimal('0')
    total_paid = repayments_qs.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    total_overdue = repayments_qs.filter(status=RepaymentStatus.OVERDUE).aggregate(
        total=Sum('total_due')
    )['total'] or Decimal('0')
    
    # Pagination
    paginator = Paginator(repayments_qs, 30)
    page_number = request.GET.get('page')
    repayments = paginator.get_page(page_number)
    
    context = {
        'institution': institution,
        'repayments': repayments,
        'status': status,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'total_due': total_due,
        'total_paid': total_paid,
        'total_overdue': total_overdue,
    }
    return render(request, 'financial/repayments.html', context)


# ============================================================
# REPORTS
# ============================================================

# core/views_financial.py - Sahihisha financial_reports

@financial_required
def financial_reports(request):
    """Generate financial reports"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    # Get date range from request
    report_type = request.GET.get('report_type', 'summary')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    else:
        date_from = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = timezone.now().date()
    else:
        date_to = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Convert to datetime for filtering
    date_from_dt = timezone.make_aware(timezone.datetime.combine(date_from, timezone.datetime.min.time()))
    date_to_dt = timezone.make_aware(timezone.datetime.combine(date_to, timezone.datetime.max.time()))
    
    # Get data for the period
    applications = LoanApplication.objects.filter(
        loan_product__institution=institution,
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt
    )
    
    disbursements = LoanDisbursement.objects.filter(
        application__loan_product__institution=institution,
        requested_at__gte=date_from_dt,
        requested_at__lte=date_to_dt
    )
    
    repayments = Repayment.objects.filter(
        loan__application__loan_product__institution=institution,
        due_date__gte=date_from,
        due_date__lte=date_to
    )
    
    payments_received = PaymentTransaction.objects.filter(
        loan__application__loan_product__institution=institution,
        confirmed_at__gte=date_from_dt,
        confirmed_at__lte=date_to_dt,
        status=PaymentTransactionStatus.CONFIRMED
    )
    
    # Summary statistics
    summary = {
        'total_applications': applications.count(),
        'total_approved': applications.filter(status__in=['APPROVED', 'FARMER_ACCEPTED', 'DISBURSEMENT_PENDING', 'DISBURSED']).count(),
        'total_rejected': applications.filter(status='REJECTED').count(),
        'total_disbursed': disbursements.filter(status='SUCCESS').aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        'total_repayments': repayments.aggregate(total=Sum('total_due'))['total'] or Decimal('0'),
        'total_recovered': payments_received.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        'total_outstanding': Loan.objects.filter(
            application__loan_product__institution=institution,
            status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE]
        ).aggregate(total=Sum('outstanding_balance'))['total'] or Decimal('0'),
    }
    
    # Monthly breakdown for chart
    monthly_data = []
    current = date_from
    
    # Import datetime for date operations
    from datetime import date as date_class
    
    while current <= date_to:
        month_start = timezone.make_aware(timezone.datetime.combine(current, timezone.datetime.min.time()))
        
        # Calculate next month correctly
        if current.month == 12:
            next_month = date_class(current.year + 1, 1, 1)
        else:
            next_month = date_class(current.year, current.month + 1, 1)
        
        month_end = timezone.make_aware(timezone.datetime.combine(next_month, timezone.datetime.min.time())) - timedelta(seconds=1)
        
        month_data = {
            'month': current.strftime('%b %Y'),
            'applications': applications.filter(created_at__gte=month_start, created_at__lte=month_end).count(),
            'disbursed': disbursements.filter(requested_at__gte=month_start, requested_at__lte=month_end, status='SUCCESS').aggregate(total=Sum('amount'))['total'] or Decimal('0'),
            'recovered': payments_received.filter(confirmed_at__gte=month_start, confirmed_at__lte=month_end).aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        }
        monthly_data.append(month_data)
        
        # Move to next month
        current = next_month
    
    context = {
        'institution': institution,
        'report_type': report_type,
        'date_from': date_from,
        'date_to': date_to,
        'summary': summary,
        'monthly_data': monthly_data,
        'applications': applications[:10],
        'disbursements': disbursements[:10],
        'repayments': repayments[:10],
    }
    return render(request, 'financial/reports.html', context)


# ============================================================
# PROFILE
# ============================================================

@financial_required
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
            institution.phone = request.user.phone or ''
            institution.email = request.user.email or ''
            institution.save()
            
            messages.success(request, "Financial institution profile created successfully!")
            return redirect('financial_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FinancialInstitutionProfileForm()
    
    context = {
        'form': form,
        'user': request.user,
    }
    return render(request, 'financial/profile_create.html', context)


@financial_required
def financial_profile_edit(request):
    """Edit financial institution profile"""
    institution = get_object_or_404(FinancialInstitution, user=request.user)
    
    if request.method == 'POST':
        form = FinancialInstitutionProfileForm(request.POST, request.FILES, instance=institution)
        if form.is_valid():
            institution = form.save(commit=False)
            # Update phone and email from user if not provided
            if not institution.phone:
                institution.phone = request.user.phone or ''
            if not institution.email:
                institution.email = request.user.email or ''
            institution.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('financial_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FinancialInstitutionProfileForm(instance=institution)
    
    context = {
        'form': form,
        'institution': institution,
        'user': request.user,
    }
    return render(request, 'financial/profile_edit.html', context)


# ============================================================
# FARMERS
# ============================================================

@financial_required
def financial_farmers(request):
    """View farmers with loan applications"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    # Get all farmers who have applied for loans with this institution
    farmers_qs = Farmer.objects.filter(
        loan_applications__loan_product__institution=institution
    ).distinct().order_by('-loan_applications__created_at')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        farmers_qs = farmers_qs.filter(
            Q(full_name__icontains=search) |
            Q(phone_number__icontains=search) |
            Q(region__icontains=search) |
            Q(district__icontains=search) |
            Q(village__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(farmers_qs, 20)
    page_number = request.GET.get('page')
    farmers = paginator.get_page(page_number)
    
    # Add stats for each farmer
    for farmer in farmers:
        farmer.loan_count = LoanApplication.objects.filter(farmer=farmer).count()
        farmer.total_borrowed = LoanApplication.objects.filter(
            farmer=farmer, status='DISBURSED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        farmer.total_repaid = Repayment.objects.filter(
            loan__application__farmer=farmer
        ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    
    context = {
        'institution': institution,
        'farmers': farmers,
        'search': search,
    }
    return render(request, 'financial/farmers.html', context)


@financial_required
def financial_farmer_detail(request, farmer_id):
    """View detailed farmer information"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    farmer = get_object_or_404(Farmer, id=farmer_id)
    
    # Get farmer's loans with this institution
    applications = LoanApplication.objects.filter(
        farmer=farmer,
        loan_product__institution=institution
    ).select_related('loan_product').order_by('-created_at')
    
    # Get all loans
    loans = Loan.objects.filter(
        application__farmer=farmer,
        application__loan_product__institution=institution
    ).select_related('application__loan_product')
    
    # Get repayments
    repayments = Repayment.objects.filter(
        loan__application__farmer=farmer,
        loan__application__loan_product__institution=institution
    ).order_by('-due_date')[:20]
    
    # Farmer statistics
    farmer.calculate_credit_readiness()
    eligibility = farmer.get_eligibility_level()
    
    # Financial summary
    total_borrowed = applications.filter(
        status__in=['DISBURSED', 'REPAID']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    total_repaid = Repayment.objects.filter(
        loan__application__farmer=farmer,
        loan__application__loan_product__institution=institution
    ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    
    total_outstanding = Loan.objects.filter(
        application__farmer=farmer,
        application__loan_product__institution=institution,
        status__in=[LoanStatus.DISBURSED, LoanStatus.ACTIVE, 
                   LoanStatus.PARTIALLY_REPAID, LoanStatus.OVERDUE]
    ).aggregate(total=Sum('outstanding_balance'))['total'] or Decimal('0')
    
    context = {
        'institution': institution,
        'farmer': farmer,
        'eligibility': eligibility,
        'applications': applications,
        'loans': loans,
        'repayments': repayments,
        'total_borrowed': total_borrowed,
        'total_repaid': total_repaid,
        'total_outstanding': total_outstanding,
    }
    return render(request, 'financial/farmer_detail.html', context)


# ============================================================
# DISBURSEMENTS
# ============================================================

@financial_required
def financial_disbursements(request):
    """View all disbursements"""
    institution = FinancialInstitution.objects.filter(user=request.user).first()
    
    if not institution:
        messages.warning(request, "Please complete your financial institution profile first.")
        return redirect('financial_profile_create')
    
    disbursements_qs = LoanDisbursement.objects.filter(
        application__loan_product__institution=institution
    ).select_related(
        'application__farmer',
        'application__loan_product',
        'loan'
    ).order_by('-requested_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        disbursements_qs = disbursements_qs.filter(status=status)
    
    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        disbursements_qs = disbursements_qs.filter(requested_at__date__gte=date_from)
    if date_to:
        disbursements_qs = disbursements_qs.filter(requested_at__date__lte=date_to)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        disbursements_qs = disbursements_qs.filter(
            Q(application__farmer__full_name__icontains=search) |
            Q(application__farmer__phone_number__icontains=search) |
            Q(provider_reference__icontains=search)
        )
    
    # Summary - BEFORE pagination
    total_amount = disbursements_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_success = disbursements_qs.filter(status='SUCCESS').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_failed = disbursements_qs.filter(status='FAILED').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_pending = disbursements_qs.filter(status='PENDING').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # Pagination
    paginator = Paginator(disbursements_qs, 20)
    page_number = request.GET.get('page')
    disbursements = paginator.get_page(page_number)
    
    context = {
        'institution': institution,
        'disbursements': disbursements,
        'status': status,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'total_amount': total_amount,
        'total_success': total_success,
        'total_failed': total_failed,
        'total_pending': total_pending,
    }
    return render(request, 'financial/disbursements.html', context)