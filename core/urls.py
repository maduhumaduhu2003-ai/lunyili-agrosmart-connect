from django.urls import path
from . import views
from .views_supplier import (
    supplier_profile_create,
    supplier_products, supplier_product_create, supplier_product_edit,
    supplier_product_delete, supplier_orders, supplier_order_detail
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
from .views_ussd import sms_callback, ussd_callback


urlpatterns = [
    # Web views
    path('', views.index_view, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    
    # Supplier URLs
    path('supplier/profile/create/', supplier_profile_create, name='supplier_profile_create'),
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
    
    # USSD endpoints
    path('ussd/', ussd_callback, name='ussd_callback'),
    path('ussd/callback/', ussd_callback, name='ussd_callback_alt'),
    path('sms-callback/', sms_callback, name='sms_callback'),
]