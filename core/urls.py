

from django.urls import path
from . import views_webhook
from . import views
from .views_supplier import (
    supplier_profile_create,
    supplier_products, supplier_product_create, supplier_product_edit,
    supplier_product_delete, supplier_orders, supplier_order_detail,
    supplier_profile_edit,
    supplier_dashboard  
)
from .views_buyer import (
    buyer_profile_create, buyer_dashboard,
    buyer_requests, buyer_request_create, buyer_request_detail,
    buyer_request_edit, buyer_request_delete, buyer_request_toggle
)
from .views_extension import (
    extension_profile_create, extension_dashboard,
    extension_advice, extension_advice_create, extension_advice_edit,
    extension_advice_delete, extension_advice_toggle, extension_advice_detail,
    extension_farmers, extension_farmer_detail
)
from .views_financial import (
    financial_profile_create, financial_dashboard,
    financial_loan_products, financial_loan_product_create,
    financial_loan_product_edit, financial_loan_product_delete,
    financial_applications, financial_application_detail,
    financial_loan_product_detail, financial_loan_product_toggle,
    financial_active_loans, financial_loan_detail,
    financial_repayments, financial_reports,
    financial_farmers, financial_farmer_detail,
    financial_disbursements, financial_profile_edit
)
from .views_ussd import sms_callback, ussd_callback, payment_callback, disbursement_callback


urlpatterns = [
    # Web views
    path('', views.index_view, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    
    # Supplier URLs
    path('supplier/dashboard/', supplier_dashboard, name='supplier_dashboard'),  
    path('supplier/profile/create/', supplier_profile_create, name='supplier_profile_create'),
    path('supplier/profile/edit/', supplier_profile_edit, name='supplier_profile_edit'),
    path('supplier/products/', supplier_products, name='supplier_products'),
    path('supplier/products/create/', supplier_product_create, name='supplier_product_create'),
    path('supplier/products/<uuid:product_id>/edit/', supplier_product_edit, name='supplier_product_edit'),
    path('supplier/products/<uuid:product_id>/delete/', supplier_product_delete, name='supplier_product_delete'),
    path('supplier/orders/', supplier_orders, name='supplier_orders'),
    path('supplier/orders/<uuid:order_id>/', supplier_order_detail, name='supplier_order_detail'),
    
    # Buyer URLs
    path('buyer/profile/create/', buyer_profile_create, name='buyer_profile_create'),
    path('buyer/dashboard/', buyer_dashboard, name='buyer_dashboard'),
    path('buyer/requests/', buyer_requests, name='buyer_requests'),
    path('buyer/requests/create/', buyer_request_create, name='buyer_request_create'),
    path('buyer/requests/<uuid:request_id>/', buyer_request_detail, name='buyer_request_detail'),
    path('buyer/requests/<uuid:request_id>/edit/', buyer_request_edit, name='buyer_request_edit'),
    path('buyer/requests/<uuid:request_id>/delete/', buyer_request_delete, name='buyer_request_delete'),
    path('buyer/requests/<uuid:request_id>/toggle/', buyer_request_toggle, name='buyer_request_toggle'),
    
    # Extension Officer URLs
    path('extension/profile/create/', extension_profile_create, name='extension_profile_create'),
    path('extension/dashboard/', extension_dashboard, name='extension_dashboard'),
    path('extension/advice/', extension_advice, name='extension_advice'),
    path('extension/advice/create/', extension_advice_create, name='extension_advice_create'),
    path('extension/advice/<uuid:advice_id>/', extension_advice_detail, name='extension_advice_detail'),
    path('extension/advice/<uuid:advice_id>/edit/', extension_advice_edit, name='extension_advice_edit'),
    path('extension/advice/<uuid:advice_id>/delete/', extension_advice_delete, name='extension_advice_delete'),
    path('extension/advice/<uuid:advice_id>/toggle/', extension_advice_toggle, name='extension_advice_toggle'),
    path('extension/farmers/', extension_farmers, name='extension_farmers'),
    path('extension/farmers/<uuid:farmer_id>/', extension_farmer_detail, name='extension_farmer_detail'),
    
    # Financial Institution URLs
    path('financial/profile/create/', financial_profile_create, name='financial_profile_create'),
    path('financial/profile/edit/', financial_profile_edit, name='financial_profile_edit'),
    path('financial/dashboard/', financial_dashboard, name='financial_dashboard'),
    path('financial/loan-products/', financial_loan_products, name='financial_loan_products'),
    path('financial/loan-products/create/', financial_loan_product_create, name='financial_loan_product_create'),
    path('financial/loan-products/<uuid:product_id>/', financial_loan_product_detail, name='financial_loan_product_detail'),
    path('financial/loan-products/<uuid:product_id>/edit/', financial_loan_product_edit, name='financial_loan_product_edit'),
    path('financial/loan-products/<uuid:product_id>/delete/', financial_loan_product_delete, name='financial_loan_product_delete'),
    path('financial/loan-products/<uuid:product_id>/toggle/', financial_loan_product_toggle, name='financial_loan_product_toggle'),
    path('financial/applications/', financial_applications, name='financial_applications'),
    path('financial/applications/<uuid:application_id>/', financial_application_detail, name='financial_application_detail'),
    path('financial/loans/', financial_active_loans, name='financial_active_loans'),
    path('financial/loans/<uuid:loan_id>/', financial_loan_detail, name='financial_loan_detail'),
    path('financial/repayments/', financial_repayments, name='financial_repayments'),
    path('financial/reports/', financial_reports, name='financial_reports'),
    path('financial/farmers/', financial_farmers, name='financial_farmers'),
    path('financial/farmers/<uuid:farmer_id>/', financial_farmer_detail, name='financial_farmer_detail'),
    path('financial/disbursements/', financial_disbursements, name='financial_disbursements'),
    
    # Webhook endpoints
    path('webhooks/clickpesa/', views_webhook.clickpesa_webhook, name='clickpesa_webhook'),
    path('webhooks/clickpesa/health/', views_webhook.clickpesa_health, name='clickpesa_health'),
    
    # USSD endpoints
    path('ussd/', ussd_callback, name='ussd_callback'),
    path('ussd/callback/', ussd_callback, name='ussd_callback_alt'),
    path('sms-callback/', sms_callback, name='sms_callback'),
    path('payments/callback/', payment_callback, name='payment_callback'),
    path('disbursements/callback/', disbursement_callback, name='disbursement_callback'),
]