"""
Extension Officer Views - Advice management and farmer support
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import ExtensionOfficer, Advice, Farmer, User
from .forms import ExtensionOfficerProfileForm, AdviceForm


@login_required
def extension_profile_create(request):
    """Create extension officer profile"""
    if ExtensionOfficer.objects.filter(user=request.user).exists():
        messages.info(request, "You already have an extension officer profile.")
        return redirect('extension_dashboard')
    
    if request.method == 'POST':
        form = ExtensionOfficerProfileForm(request.POST)
        if form.is_valid():
            officer = form.save(commit=False)
            officer.user = request.user
            officer.save()
            messages.success(request, "Extension officer profile created successfully!")
            return redirect('extension_dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ExtensionOfficerProfileForm()
    
    return render(request, 'extension/profile_create.html', {'form': form})


@login_required
def extension_dashboard(request):
    """Extension Officer dashboard"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    # Get advice articles
    advice = Advice.objects.filter(author=officer).order_by('-created_at')
    total_advice = advice.count()
    published_advice = advice.filter(is_published=True).count()
    recent_advice = advice[:5]
    
    # Get farmers in officer's region
    if officer.region:
        farmers = Farmer.objects.filter(region__icontains=officer.region)
        total_farmers = farmers.count()
        active_farmers = farmers.filter(is_active=True).count()
    else:
        total_farmers = Farmer.objects.count()
        active_farmers = Farmer.objects.filter(is_active=True).count()
    
    context = {
        'officer': officer,
        'total_advice': total_advice,
        'published_advice': published_advice,
        'recent_advice': recent_advice,
        'total_farmers': total_farmers,
        'active_farmers': active_farmers,
    }
    return render(request, 'dashboards/extension_officer.html', context)


@login_required
def extension_advice(request):
    """List all advice articles"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    # Get advice
    advice = Advice.objects.filter(author=officer).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status == 'published':
        advice = advice.filter(is_published=True)
    elif status == 'draft':
        advice = advice.filter(is_published=False)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        advice = advice.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search) |
            Q(crop__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(advice, 10)
    page_number = request.GET.get('page')
    advice = paginator.get_page(page_number)
    
    # Status counts
    all_advice = Advice.objects.filter(author=officer)
    status_counts = {
        'published': all_advice.filter(is_published=True).count(),
        'draft': all_advice.filter(is_published=False).count(),
    }
    
    context = {
        'officer': officer,
        'advice': advice,
        'status': status,
        'status_counts': status_counts,
        'search': search,
    }
    return render(request, 'extension/advice.html', context)


@login_required
def extension_advice_create(request):
    """Create new advice article"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    if request.method == 'POST':
        form = AdviceForm(request.POST, request.FILES)
        if form.is_valid():
            advice = form.save(commit=False)
            advice.author = officer
            advice.save()
            messages.success(request, f"Advice article '{advice.title}' created successfully!")
            return redirect('extension_advice')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdviceForm()
    
    context = {
        'officer': officer,
        'form': form,
        'action': 'Create',
    }
    return render(request, 'extension/advice_form.html', context)


@login_required
def extension_advice_edit(request, advice_id):
    """Edit advice article"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    advice = get_object_or_404(Advice, id=advice_id, author=officer)
    
    if request.method == 'POST':
        form = AdviceForm(request.POST, request.FILES, instance=advice)
        if form.is_valid():
            form.save()
            messages.success(request, f"Advice article '{advice.title}' updated successfully!")
            return redirect('extension_advice')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdviceForm(instance=advice)
    
    context = {
        'officer': officer,
        'form': form,
        'action': 'Edit',
        'advice': advice,
    }
    return render(request, 'extension/advice_form.html', context)


@login_required
def extension_advice_delete(request, advice_id):
    """Delete advice article"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    advice = get_object_or_404(Advice, id=advice_id, author=officer)
    
    if request.method == 'POST':
        title = advice.title
        advice.delete()
        messages.success(request, f"Advice article '{title}' deleted successfully!")
        return redirect('extension_advice')
    
    context = {
        'officer': officer,
        'advice': advice,
    }
    return render(request, 'extension/advice_confirm_delete.html', context)


@login_required
def extension_advice_toggle(request, advice_id):
    """Toggle advice publish status"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    advice = get_object_or_404(Advice, id=advice_id, author=officer)
    
    if request.method == 'POST':
        advice.is_published = not advice.is_published
        advice.published_date = timezone.now() if advice.is_published else None
        advice.save()
        status = "published" if advice.is_published else "unpublished"
        messages.success(request, f"Advice article '{advice.title}' {status} successfully!")
        return redirect('extension_advice')
    
    context = {
        'officer': officer,
        'advice': advice,
    }
    return render(request, 'extension/advice_toggle.html', context)


@login_required
def extension_advice_detail(request, advice_id):
    """View advice article details"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    advice = get_object_or_404(Advice, id=advice_id, author=officer)
    
    context = {
        'officer': officer,
        'advice': advice,
    }
    return render(request, 'extension/advice_detail.html', context)


@login_required
def extension_farmers(request):
    """View farmers in officer's region"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    # Get farmers
    if officer.region:
        farmers = Farmer.objects.filter(region__icontains=officer.region).order_by('-created_at')
    else:
        farmers = Farmer.objects.all().order_by('-created_at')
    
    # Search
    search = request.GET.get('search', '')
    if search:
        farmers = farmers.filter(
            Q(full_name__icontains=search) |
            Q(phone_number__icontains=search) |
            Q(village__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(farmers, 20)
    page_number = request.GET.get('page')
    farmers = paginator.get_page(page_number)
    
    context = {
        'officer': officer,
        'farmers': farmers,
        'search': search,
    }
    return render(request, 'extension/farmers.html', context)


@login_required
def extension_farmer_detail(request, farmer_id):
    """View farmer details"""
    officer = ExtensionOfficer.objects.filter(user=request.user).first()
    
    if not officer:
        messages.warning(request, "Please complete your extension officer profile first.")
        return redirect('extension_profile_create')
    
    farmer = get_object_or_404(Farmer, id=farmer_id)
    
    context = {
        'officer': officer,
        'farmer': farmer,
    }
    return render(request, 'extension/farmer_detail.html', context)