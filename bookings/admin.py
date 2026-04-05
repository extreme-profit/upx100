from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Админка для управления заявками на запись с расширенными функциями"""
    
    list_display = ('id', 'client_name_display', 'service_link', 'time_slot_display', 'status_badge', 'company_link', 'created_at_display')
    list_filter = ('status', 'service', 'service__company', 'created_at')
    search_fields = ('client_name', 'client_email', 'service__name', 'service__company__name')
    readonly_fields = ('created_at', 'updated_at', 'confirmed_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основное', {
            'fields': ('service', 'time_slot', 'client')
        }),
        ('Данные клиента', {
            'fields': ('client_name', 'client_email', 'client_phone'),
            'description': 'Контактная информация клиента для связи'
        }),
        ('Примечание', {
            'fields': ('notes',),
            'description': 'Дополнительная информация от клиента'
        }),
        ('Статус', {
            'fields': ('status',),
            'description': 'Управление статусом заявки'
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'confirmed_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'confirm_bookings', 
        'cancel_bookings', 
        'mark_as_completed', 
        'mark_as_no_show',
        'export_selected_bookings'
    ]
    
    def client_name_display(self, obj):
        """Отображение имени клиента с ссылкой если зарегистрирован"""
        if obj.client:
            return format_html('<a href="{}">{}</a>', 
                f'/admin/accounts/user/{obj.client.id}/change/', 
                obj.client_name
            )
        return obj.client_name
    client_name_display.short_description = _('Клиент')
    
    def service_link(self, obj):
        """Ссылка на услугу"""
        return format_html('<a href="{}">{}</a>', 
            f'/admin/services/service/{obj.service.id}/change/', 
            obj.service.name
        )
    service_link.short_description = _('Услуга')
    
    def time_slot_display(self, obj):
        """Отображение временного слота"""
        if obj.time_slot:
            return format_html('{} {}', obj.time_slot.date, obj.time_slot.start_time)
        return format_html('<span style="color: gray;">Не указан</span>')
    time_slot_display.short_description = _('Время')
    
    def status_badge(self, obj):
        """Цветовой бейдж статуса заявки"""
        colors = {
            'pending': 'orange',
            'confirmed': 'green',
            'cancelled': 'red',
            'completed': 'blue',
            'no_show': 'gray',
        }
        labels = {
            'pending': '○ Ожидает',
            'confirmed': '✓ Подтверждена',
            'cancelled': '✗ Отменена',
            'completed': '● Выполнена',
            'no_show': '⚠ Не явился',
        }
        color = colors.get(obj.status, 'gray')
        label = labels.get(obj.status, obj.status)
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, label)
    status_badge.short_description = _('Статус')
    
    def company_link(self, obj):
        """Ссылка на компанию"""
        company = obj.service.company
        return format_html('<a href="{}">{}</a>', 
            f'/admin/companies/company/{company.id}/change/', 
            company.name
        )
    company_link.short_description = _('Компания')
    
    def created_at_display(self, obj):
        """Дата создания в удобном формате"""
        return obj.created_at.strftime('%d.%m.%Y %H:%M')
    created_at_display.short_description = _('Создана')
    
    @admin.action(description='Подтвердить выбранные заявки')
    def confirm_bookings(self, request, queryset):
        """Подтверждение заявок"""
        confirmed_count = 0
        for booking in queryset.filter(status='pending'):
            booking.confirm_booking()
            confirmed_count += 1
        self.message_user(request, f'Подтверждено заявок: {confirmed_count}')
    
    @admin.action(description='Отменить выбранные заявки')
    def cancel_bookings(self, request, queryset):
        """Отмена заявок"""
        cancelled_count = 0
        for booking in queryset.filter(status__in=['pending', 'confirmed']):
            booking.cancel_booking()
            cancelled_count += 1
        self.message_user(request, f'Отменено заявок: {cancelled_count}')
    
    @admin.action(description='Отметить как выполненные')
    def mark_as_completed(self, request, queryset):
        """Отметка заявок как выполненных"""
        updated = queryset.filter(status='confirmed').update(status='completed')
        self.message_user(request, f'Отмечено как выполненные: {updated} заявок')
    
    @admin.action(description='Отметить как "Не явился"')
    def mark_as_no_show(self, request, queryset):
        """Отметка клиентов как не явившихся"""
        updated = queryset.filter(status='confirmed').update(status='no_show')
        # Освобождаем слоты
        for booking in queryset.filter(status='confirmed'):
            if booking.time_slot:
                booking.time_slot.is_booked = False
                booking.time_slot.save()
        self.message_user(request, f'Отмечено как "Не явился": {updated} заявок')
    
    @admin.action(description='Экспортировать выбранные заявки (CSV)')
    def export_selected_bookings(self, request, queryset):
        """Экспорт заявок в CSV формате"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="bookings_export.csv"'
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'ID', 'Дата создания', 'Клиент', 'Email', 'Телефон',
            'Услуга', 'Компания', 'Дата записи', 'Время', 'Статус', 'Примечание'
        ])
        
        for booking in queryset:
            writer.writerow([
                booking.id,
                booking.created_at.strftime('%d.%m.%Y %H:%M'),
                booking.client_name,
                booking.client_email,
                booking.client_phone or '',
                booking.service.name,
                booking.service.company.name,
                booking.time_slot.date if booking.time_slot else '',
                booking.time_slot.start_time if booking.time_slot else '',
                booking.get_status_display(),
                booking.notes or ''
            ])
        
        self.message_user(request, f'Экспортировано {queryset.count()} заявок')
        return response
