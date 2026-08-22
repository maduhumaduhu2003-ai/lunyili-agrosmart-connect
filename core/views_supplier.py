"""
Supplier Views - Product management and orders
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import Product, Category, Supplier, Order, OrderItem
from .forms import ProductForm, SupplierProfileForm


@login_required
def supplier_profile_create(request):
    """Create supplier profile - auto-fill phone and email from User"""
    
    if Supplier.objects.filter(user=request.user).exists():
        messages.info(request, "You already have a supplier profile.")
        return redirect('supplier_products')
    
    if request.method == 'POST':
        form = SupplierProfileForm(request.POST, request.FILES)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.user = request.user
            
            # ✅ Auto-fill phone and email from User model
            supplier.phone = request.user.phone or ''
            supplier.email = request.user.email or ''
            
            supplier.save()
            messages.success(request, f"Supplier profile '{supplier.company_name}' created successfully!")
            return redirect('supplier_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SupplierProfileForm()
    
    context = {
        'form': form,
        'user': request.user,  
    }
    return render(request, 'supplier/profile_create.html', context)


@login_required
def supplier_products(request):
    """List all products for the supplier"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    products = Product.objects.filter(supplier=supplier).order_by('-created_at')
    
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(name__icontains=search) | 
            Q(description__icontains=search) |
            Q(category__name__icontains=search)
        )
    
    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)
    
    context = {
        'supplier': supplier,
        'products': products,
        'search': search,
    }
    return render(request, 'supplier/products.html', context)


@login_required
def supplier_product_create(request):
    """Create a new product - FULL PAGE"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.supplier = supplier
            product.save()
            messages.success(request, f"Product '{product.name}' created successfully!")
            return redirect('supplier_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProductForm()
    
    # Get all categories for display
    categories = Category.objects.all().order_by('name')
    
    context = {
        'form': form,
        'action': 'Create',
        'categories': categories,
        'supplier': supplier,
    }
    return render(request, 'supplier/product_form.html', context)


@login_required
def supplier_product_edit(request, product_id):
    """Edit an existing product"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    product = get_object_or_404(Product, id=product_id, supplier=supplier)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Product '{product.name}' updated successfully!")
            return redirect('supplier_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProductForm(instance=product)
    
    categories = Category.objects.all().order_by('name')
    
    context = {
        'form': form,
        'action': 'Edit',
        'product': product,
        'categories': categories,
        'supplier': supplier,
    }
    return render(request, 'supplier/product_form.html', context)


@login_required
def supplier_product_delete(request, product_id):
    """Delete a product"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    product = get_object_or_404(Product, id=product_id, supplier=supplier)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f"Product '{product_name}' deleted successfully!")
        return redirect('supplier_products')
    
    return render(request, 'supplier/product_confirm_delete.html', {'product': product})


@login_required
def supplier_orders(request):
    """List all orders for the supplier"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    orders = Order.objects.filter(supplier=supplier).order_by('-created_at')
    
    status = request.GET.get('status', '')
    if status:
        orders = orders.filter(status=status)
    
    search = request.GET.get('search', '')
    if search:
        orders = orders.filter(
            Q(reference__icontains=search) |
            Q(farmer__full_name__icontains=search) |
            Q(farmer__phone_number__icontains=search)
        )
    
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    orders = paginator.get_page(page_number)
    
    status_counts = {
        'PENDING': Order.objects.filter(supplier=supplier, status='PENDING').count(),
        'PROCESSING': Order.objects.filter(supplier=supplier, status='PROCESSING').count(),
        'PAYMENT_PENDING': Order.objects.filter(supplier=supplier, status='PAYMENT_PENDING').count(),
        'DISPATCHED': Order.objects.filter(supplier=supplier, status='DISPATCHED').count(),
        'DELIVERED': Order.objects.filter(supplier=supplier, status='DELIVERED').count(),
        'CANCELLED': Order.objects.filter(supplier=supplier, status='CANCELLED').count(),
    }
    
    context = {
        'orders': orders,
        'status': status,
        'status_counts': status_counts,
        'search': search,
    }
    return render(request, 'supplier/orders.html', context)


@login_required
def supplier_order_detail(request, order_id):
    """View order details"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    order = get_object_or_404(Order, id=order_id, supplier=supplier)
    items = order.items.all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept' and order.status in ['PENDING', 'SUPPLIER_PAID']:
            order.status = 'PROCESSING'
            order.save()
            messages.success(request, f"Order {order.reference} accepted!")
            return redirect('supplier_order_detail', order_id=order.id)
            
        elif action == 'dispatch' and order.status == 'PROCESSING':
            order.status = 'DISPATCHED'
            order.save()
            messages.success(request, f"Order {order.reference} dispatched!")
            return redirect('supplier_order_detail', order_id=order.id)
            
        elif action == 'deliver':
            order.status = 'DELIVERED'
            order.delivered_date = timezone.now()
            order.save()
            messages.success(request, f"Order {order.reference} delivered!")
            return redirect('supplier_order_detail', order_id=order.id)
            
        elif action == 'cancel':
            order.status = 'CANCELLED'
            order.save()
            messages.success(request, f"Order {order.reference} cancelled!")
            return redirect('supplier_orders')
    
    context = {
        'order': order,
        'items': items,
    }
    return render(request, 'supplier/order_detail.html', context)


@login_required
def supplier_profile_edit(request):
    """Edit supplier profile with location"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    if request.method == 'POST':
        form = SupplierProfileForm(request.POST, request.FILES, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('supplier_products')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SupplierProfileForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
    }
    return render(request, 'supplier/profile_edit.html', context)

@login_required
def supplier_dashboard(request):
    """Supplier dashboard view"""
    supplier = Supplier.objects.filter(user=request.user).first()
    
    if not supplier:
        messages.warning(request, "Please complete your supplier profile first.")
        return redirect('supplier_profile_create')
    
    # Get dashboard data
    from .views import get_supplier_dashboard_data
    context = get_supplier_dashboard_data(request.user)
    
    return render(request, 'dashboards/supplier.html', context)