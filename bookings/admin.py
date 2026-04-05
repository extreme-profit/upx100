from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'service', 'time_slot', 'status', 'client_email', 'created_at')
    list_filter = ('status', 'service', 'created_at')
    search_fields = ('client_name', 'client_email', 'service__name')
    readonly_fields = ('created_at', 'updated_at', 'confirmed_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('service', 'time_slot', 'client')
        }),
        ('Данные клиента', {
            'fields': ('client_name', 'client_email', 'client_phone')
        }),
        ('Примечание', {
            'fields': ('notes',)
        }),
        ('Статус', {
            'fields': ('status',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'confirmed_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['confirm_bookings', 'cancel_bookings']
    
    def confirm_bookings(self, request, queryset):
        for booking in queryset:
            booking.confirm_booking()
        self.message_user(request, f"{queryset.count()} заявок подтверждено")
    confirm_bookings.short_description = "Подтвердить выбранные заявки"
    
    def cancel_bookings(self, request, queryset):
        for booking in queryset:
            booking.cancel_booking()
        self.message_user(request, f"{queryset.count()} заявок отменено")
    cancel_bookings.short_description = "Отменить выбранные заявки"
