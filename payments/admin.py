from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('service', 'amount', 'currency', 'status', 'paid_at', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('service__name', 'payment_id', 'service__company__name')
    readonly_fields = ('created_at', 'updated_at', 'paid_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('service', 'amount', 'currency')
        }),
        ('Статус', {
            'fields': ('status', 'payment_id', 'payment_url')
        }),
        ('Описание', {
            'fields': ('description',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_paid']
    
    def mark_as_paid(self, request, queryset):
        for payment in queryset.filter(status='pending'):
            payment.mark_as_paid()
        self.message_user(request, f"{queryset.count()} платежей обработано")
    mark_as_paid.short_description = "Отметить выбранные платежи как оплаченные"
