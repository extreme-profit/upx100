from django.contrib import admin
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'client_name', 'service', 'status', 'created_at']
    list_filter = ['status', 'service__provider']
    search_fields = ['client_name', 'client_email', 'service__name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at']
