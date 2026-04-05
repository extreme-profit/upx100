from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Админка для управления платежами с расширенными функциями"""
    
    list_display = ('id', 'service_link', 'company_link', 'amount_display', 'currency', 'status_badge', 'paid_at_display', 'created_at_display')
    list_filter = ('status', 'currency', 'created_at', 'service__company')
    search_fields = ('service__name', 'payment_id', 'service__company__name', 'service__company__owner__username')
    readonly_fields = ('created_at', 'updated_at', 'paid_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основное', {
            'fields': ('service', 'amount', 'currency'),
            'description': 'Основная информация о платеже'
        }),
        ('Статус и идентификаторы', {
            'fields': ('status', 'payment_id', 'payment_url'),
            'description': 'Статус платежа и идентификатор в платёжной системе'
        }),
        ('Описание', {
            'fields': ('description',),
            'description': 'Дополнительное описание платежа'
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'mark_as_paid', 
        'mark_as_failed', 
        'refund_payments',
        'export_selected_payments'
    ]
    
    def service_link(self, obj):
        """Ссылка на услугу"""
        return format_html('<a href="{}">{}</a>', 
            f'/admin/services/service/{obj.service.id}/change/', 
            obj.service.name
        )
    service_link.short_description = _('Услуга')
    
    def company_link(self, obj):
        """Ссылка на компанию"""
        company = obj.service.company
        return format_html('<a href="{}">{}</a>', 
            f'/admin/companies/company/{company.id}/change/', 
            company.name
        )
    company_link.short_description = _('Компания')
    
    def amount_display(self, obj):
        """Отображение суммы с форматированием"""
        return format_html('<b>{:,.2f} {}</b>', float(obj.amount), obj.currency)
    amount_display.short_description = _('Сумма')
    
    def status_badge(self, obj):
        """Цветовой бейдж статуса платежа"""
        colors = {
            'pending': 'orange',
            'success': 'green',
            'failed': 'red',
            'refunded': 'gray',
        }
        labels = {
            'pending': '○ Ожидает',
            'success': '✓ Успешно',
            'failed': '✗ Неудачно',
            'refunded': '↺ Возвращён',
        }
        color = colors.get(obj.status, 'gray')
        label = labels.get(obj.status, obj.status)
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, label)
    status_badge.short_description = _('Статус')
    
    def paid_at_display(self, obj):
        """Дата оплаты в удобном формате"""
        if obj.paid_at:
            return obj.paid_at.strftime('%d.%m.%Y %H:%M')
        return format_html('<span style="color: gray;">Не оплачено</span>')
    paid_at_display.short_description = _('Оплачено')
    
    def created_at_display(self, obj):
        """Дата создания в удобном формате"""
        return obj.created_at.strftime('%d.%m.%Y %H:%M')
    created_at_display.short_description = _('Создан')
    
    @admin.action(description='Отметить выбранные платежи как оплаченные')
    def mark_as_paid(self, request, queryset):
        """Обработка платежей как успешных"""
        processed_count = 0
        for payment in queryset.filter(status='pending'):
            payment.mark_as_paid()
            processed_count += 1
        self.message_user(request, f'Обработано платежей: {processed_count}')
    
    @admin.action(description='Отметить как неудачные')
    def mark_as_failed(self, request, queryset):
        """Отметка платежей как неудачных"""
        updated = queryset.filter(status='pending').update(status='failed')
        self.message_user(request, f'Отмечено как неудачные: {updated} платежей')
    
    @admin.action(description='Оформить возврат')
    def refund_payments(self, request, queryset):
        """Возврат платежей"""
        # Возвращаем только успешные платежи
        updated = queryset.filter(status='success').update(status='refunded')
        # Деактивируем соответствующие услуги
        for payment in queryset.filter(status='success'):
            service = payment.service
            service.status = 'inactive'
            service.is_active = False
            service.save()
        self.message_user(request, f'Оформлен возврат по {updated} платежам')
    
    @admin.action(description='Экспортировать выбранные платежи (CSV)')
    def export_selected_payments(self, request, queryset):
        """Экспорт платежей в CSV формате"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'ID', 'Дата создания', 'Дата оплаты', 'Услуга', 'Компания',
            'Сумма', 'Валюта', 'Статус', 'ID платежа', 'Описание'
        ])
        
        for payment in queryset:
            writer.writerow([
                payment.id,
                payment.created_at.strftime('%d.%m.%Y %H:%M'),
                payment.paid_at.strftime('%d.%m.%Y %H:%M') if payment.paid_at else '',
                payment.service.name,
                payment.service.company.name,
                f'{float(payment.amount):.2f}',
                payment.currency,
                payment.get_status_display(),
                payment.payment_id or '',
                payment.description or ''
            ])
        
        self.message_user(request, f'Экспортировано {queryset.count()} платежей')
        return response
