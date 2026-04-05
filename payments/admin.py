from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'service', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'currency', 'service__provider']
    search_fields = ['service__name', 'payment_id']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'paid_at']
