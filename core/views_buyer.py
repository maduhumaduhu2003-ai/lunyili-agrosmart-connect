"""
Buyer Views - Buying requests management
Buyer creates buying requests for crops they want to purchase from farmers
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import Buyer, BuyingRequest, Farmer, InterestedFarmer
from .forms import BuyerProfileForm, BuyingRequestForm


@login_required
def buyer_profile_create(request):
    """Create buyer profile"""
    if Buyer.objects.filter(user=request.user).exists():
        messages.info(request, "You already have a buyer profile.")
        return redirect('buyer_dashboard')
    
    if request.method == 'POST':
        form = BuyerProfileForm(request.POST)
        if form.is_valid():
            buyer = form.save(commit=False)
            buyer.user = request.user
            buyer.save()
            messages.success(request, "Buyer profile created successfully!")
            return redirect('buyer_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BuyerProfileForm()
    
    return render(request, 'buyer/profile_create.html', {'form': form})


@login_required
def buyer_dashboard(request):
    """Buyer dashboard - shows buying requests and interested farmers"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    # Get buying requests
    requests = BuyingRequest.objects.filter(buyer=buyer).order_by('-created_at')
    total_requests = requests.count()
    open_requests = requests.filter(is_open=True).count()
    closed_requests = requests.filter(is_open=False).count()
    recent_requests = requests[:5]
    
    # Get ALL interested farmers for this buyer
    interested_farmers = []
    interested_farmers_count = 0
    
    # Direct query - get all interested farmers for this buyer's requests
    all_interested = InterestedFarmer.objects.filter(
        buying_request__buyer=buyer
    ).select_related('farmer', 'buying_request').order_by('-created_at')
    
    # Group by buying request
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
    
    # Debug info (remove in production)
    print(f"Buyer: {buyer}")
    print(f"Total Interested: {all_interested.count()}")
    print(f"Grouped: {len(interested_farmers)}")
    
    context = {
        'buyer': buyer,
        'total_requests': total_requests,
        'open_requests': open_requests,
        'closed_requests': closed_requests,
        'recent_requests': recent_requests,
        'interested_farmers': interested_farmers,
        'interested_farmers_count': interested_farmers_count,
    }
    return render(request, 'dashboards/buyer.html', context)


@login_required
def buyer_requests(request):
    """View all buying requests"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    # Get buying requests
    requests = BuyingRequest.objects.filter(buyer=buyer).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status == 'open':
        requests = requests.filter(is_open=True)
    elif status == 'closed':
        requests = requests.filter(is_open=False)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        requests = requests.filter(
            Q(crop__icontains=search) |
            Q(location__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(requests, 10)
    page_number = request.GET.get('page')
    requests = paginator.get_page(page_number)
    
    # Status counts
    all_requests = BuyingRequest.objects.filter(buyer=buyer)
    status_counts = {
        'open': all_requests.filter(is_open=True).count(),
        'closed': all_requests.filter(is_open=False).count(),
    }
    
    context = {
        'buyer': buyer,
        'requests': requests,
        'status': status,
        'status_counts': status_counts,
        'search': search,
    }
    return render(request, 'buyer/requests.html', context)


@login_required
def buyer_request_create(request):
    """Create a new buying request"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    if request.method == 'POST':
        form = BuyingRequestForm(request.POST)
        if form.is_valid():
            buying_request = form.save(commit=False)
            buying_request.buyer = buyer
            buying_request.save()
            messages.success(request, f"Buying request for {buying_request.crop} created successfully!")
            return redirect('buyer_requests')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BuyingRequestForm()
    
    context = {
        'buyer': buyer,
        'form': form,
        'action': 'Create',
    }
    return render(request, 'buyer/request_form.html', context)


@login_required
def buyer_request_edit(request, request_id):
    """Edit a buying request"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    buying_request = get_object_or_404(BuyingRequest, id=request_id, buyer=buyer)
    
    if request.method == 'POST':
        form = BuyingRequestForm(request.POST, instance=buying_request)
        if form.is_valid():
            form.save()
            messages.success(request, f"Buying request for {buying_request.crop} updated successfully!")
            return redirect('buyer_requests')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BuyingRequestForm(instance=buying_request)
    
    context = {
        'buyer': buyer,
        'form': form,
        'action': 'Edit',
        'buying_request': buying_request,
    }
    return render(request, 'buyer/request_form.html', context)


@login_required
def buyer_request_delete(request, request_id):
    """Delete a buying request"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    buying_request = get_object_or_404(BuyingRequest, id=request_id, buyer=buyer)
    
    if request.method == 'POST':
        crop_name = buying_request.crop
        buying_request.delete()
        messages.success(request, f"Buying request for {crop_name} deleted successfully!")
        return redirect('buyer_requests')
    
    context = {
        'buyer': buyer,
        'buying_request': buying_request,
    }
    return render(request, 'buyer/request_confirm_delete.html', context)


@login_required
def buyer_request_toggle(request, request_id):
    """Toggle buying request status (open/closed)"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    buying_request = get_object_or_404(BuyingRequest, id=request_id, buyer=buyer)
    
    if request.method == 'POST':
        buying_request.is_open = not buying_request.is_open
        buying_request.save()
        status = "opened" if buying_request.is_open else "closed"
        messages.success(request, f"Buying request for {buying_request.crop} {status} successfully!")
        return redirect('buyer_requests')
    
    context = {
        'buyer': buyer,
        'buying_request': buying_request,
    }
    return render(request, 'buyer/request_toggle.html', context)


@login_required
def buyer_request_detail(request, request_id):
    """View buying request details and interested farmers"""
    buyer = Buyer.objects.filter(user=request.user).first()
    
    if not buyer:
        messages.warning(request, "Please complete your buyer profile first.")
        return redirect('buyer_profile_create')
    
    buying_request = get_object_or_404(BuyingRequest, id=request_id, buyer=buyer)
    
    # Get interested farmers
    interested_farmers = InterestedFarmer.objects.filter(
        buying_request=buying_request
    ).select_related('farmer').order_by('-created_at')
    
    context = {
        'buyer': buyer,
        'buying_request': buying_request,
        'interested_farmers': interested_farmers,
    }
    return render(request, 'buyer/request_detail.html', context)