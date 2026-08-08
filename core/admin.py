from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *

# User Admin
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'full_name', 'role', 'is_verified', 'is_active']
    list_filter = ['role', 'is_verified', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'address')}),
        ('Profile', {'fields': ('profile_photo', 'role', 'is_verified')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )

# Register all models
admin.site.register(Farmer)
admin.site.register(Supplier)
admin.site.register(Buyer)
admin.site.register(ExtensionOfficer)
admin.site.register(FinancialInstitution)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(LoanProduct)
admin.site.register(LoanApplication)
admin.site.register(Advice)
admin.site.register(WeatherData)
admin.site.register(WeatherAlert)
admin.site.register(MarketPrice)
admin.site.register(BuyingRequest)
admin.site.register(SMSTemplate)
admin.site.register(SMSMessage)
admin.site.register(USSDSession)
admin.site.register(USSDLog)