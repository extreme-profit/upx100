from django.contrib import admin
from .models import Service, TimeSlot


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'employee', 'price', 'status', 'is_active', 'created_at')
    list_filter = ('status', 'is_active', 'subcategory', 'company')
    search_fields = ('name', 'description', 'company__name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'employee', 'subcategory', 'name', 'description')
        }),
        ('Параметры', {
            'fields': ('price', 'duration_minutes')
        }),
        ('Медиа', {
            'fields': ('photo',)
        }),
        ('Статус и оплата', {
            'fields': ('status', 'is_active', 'paid_until')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('service', 'date', 'start_time', 'end_time', 'is_booked', 'is_active')
    list_filter = ('date', 'is_booked', 'is_active', 'service')
    search_fields = ('service__name',)
    readonly_fields = ('created_at',)
    ordering = ('date', 'start_time')
    
    fieldsets = (
        ('Слот', {
            'fields': ('service', 'date', 'start_time', 'end_time')
        }),
        ('Статус', {
            'fields': ('is_booked', 'is_active')
        }),
        ('Даты', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
