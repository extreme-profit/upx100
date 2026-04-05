from django.contrib import admin
from .models import Company, Employee, ServiceCategory, Service, ServiceTimeSlot, Booking, Payment


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'address', 'created_at']
    search_fields = ['name', 'owner__username', 'address']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'position', 'is_active', 'created_at']
    list_filter = ['company', 'is_active']
    search_fields = ['name', 'company__name']


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'category', 'employee', 'price', 'duration', 'status', 'payment_due_date']
    list_filter = ['status', 'company', 'category']
    search_fields = ['name', 'company__name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ServiceTimeSlot)
class ServiceTimeSlotAdmin(admin.ModelAdmin):
    list_display = ['service', 'date', 'start_time', 'end_time', 'is_booked']
    list_filter = ['date', 'is_booked', 'service']
    search_fields = ['service__name']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'service', 'status', 'created_at']
    list_filter = ['status', 'service']
    search_fields = ['client_name', 'client_phone', 'service__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['service', 'amount', 'status', 'payment_date', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['service__name', 'transaction_id']
    readonly_fields = ['created_at']
