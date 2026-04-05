from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from .models import Service, TimeSlot


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Админка для управления услугами с расширенным функционалом"""
    
    list_display = ('name', 'company', 'employee_link', 'price', 'duration_display', 'status_badge', 'is_active_status', 'paid_until_date', 'services_count')
    list_filter = ('status', 'is_active', 'subcategory', 'company', 'employee')
    search_fields = ('name', 'description', 'company__name', 'employee__name')
    readonly_fields = ('created_at', 'updated_at', 'embedding_preview')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
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
            'fields': ('status', 'is_active', 'paid_until'),
            'description': 'Управление статусом оплаты и активностью услуги'
        }),
        ('Векторный поиск', {
            'fields': ('embedding_preview',),
            'classes': ('collapse',),
            'description': 'Данные для векторного поиска FAISS'
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'activate_services', 
        'deactivate_services', 
        'extend_payment_30_days', 
        'extend_payment_7_days',
        'mark_as_pending_payment'
    ]
    
    def employee_link(self, obj):
        """Ссылка на сотрудника"""
        if obj.employee:
            return format_html('<a href="{}">{}</a>', 
                f'/admin/companies/employee/{obj.employee.id}/change/', 
                obj.employee.name
            )
        return format_html('<span style="color: gray;">Не указан</span>')
    employee_link.short_description = _('Сотрудник')
    
    def duration_display(self, obj):
        """Отображение длительности услуги"""
        hours = obj.duration_minutes // 60
        minutes = obj.duration_minutes % 60
        if hours > 0:
            return f"{hours}ч {minutes}м" if minutes > 0 else f"{hours}ч"
        return f"{minutes}м"
    duration_display.short_description = _('Длительность')
    
    def status_badge(self, obj):
        """Цветовой бейдж статуса услуги"""
        colors = {
            'pending_payment': 'orange',
            'active': 'green',
            'inactive': 'gray',
            'expired': 'red',
        }
        labels = {
            'pending_payment': '○ Ожидает оплаты',
            'active': '✓ Активна',
            'inactive': '✗ Неактивна',
            'expired': '⚠ Истекла',
        }
        color = colors.get(obj.status, 'gray')
        label = labels.get(obj.status, obj.status)
        return format_html('<span style="color: {};">{}</span>', color, label)
    status_badge.short_description = _('Статус')
    
    def is_active_status(self, obj):
        """Статус активности с цветовой индикацией"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Да</span>')
        return format_html('<span style="color: red;">✗ Нет</span>')
    is_active_status.short_description = _('Активна')
    
    def paid_until_date(self, obj):
        """Дата окончания оплаты"""
        if obj.paid_until:
            now = timezone.now()
            if obj.paid_until < now:
                return format_html('<span style="color: red;">Истекла: {}</span>', obj.paid_until.strftime('%d.%m.%Y'))
            days_left = (obj.paid_until - now).days
            if days_left <= 3:
                return format_html('<span style="color: orange;">{} (ост. {} дн.)</span>', obj.paid_until.strftime('%d.%m.%Y'), days_left)
            return format_html('<span style="color: green;">{}</span>', obj.paid_until.strftime('%d.%m.%Y'))
        return format_html('<span style="color: gray;">Не оплачено</span>')
    paid_until_date.short_description = _('Оплачено до')
    
    def services_count(self, obj):
        """Количество временных слотов"""
        count = obj.time_slots.count()
        booked = obj.time_slots.filter(is_booked=True).count()
        return format_html('<b>{}</b> / {}', booked, count)
    services_count.short_description = _('Слоты')
    
    def embedding_preview(self, obj):
        """Предпросмотр векторного представления"""
        if obj.embedding:
            return format_html('<span style="color: green;">✓ Вектор задан ({} байт)</span>', len(obj.embedding))
        return format_html('<span style="color: orange;">○ Вектор не задан</span>')
    embedding_preview.short_description = _('Векторное представление')
    
    @admin.action(description='Активировать выбранные услуги')
    def activate_services(self, request, queryset):
        """Активация услуг"""
        updated = queryset.update(is_active=True, status='active')
        self.message_user(request, f'Активировано услуг: {updated}')
    
    @admin.action(description='Деактивировать выбранные услуги')
    def deactivate_services(self, request, queryset):
        """Деактивация услуг"""
        updated = queryset.update(is_active=False, status='inactive')
        self.message_user(request, f'Деактивировано услуг: {updated}')
    
    @admin.action(description='Продлить оплату на 30 дней')
    def extend_payment_30_days(self, request, queryset):
        """Продление оплаты на 30 дней"""
        now = timezone.now()
        for service in queryset:
            if service.paid_until and service.paid_until > now:
                service.paid_until = service.paid_until + timedelta(days=30)
            else:
                service.paid_until = now + timedelta(days=30)
            service.status = 'active'
            service.is_active = True
            service.save()
        self.message_user(request, f'Продлено услуг: {queryset.count()} (на 30 дней)')
    
    @admin.action(description='Продлить оплату на 7 дней')
    def extend_payment_7_days(self, request, queryset):
        """Продление оплаты на 7 дней"""
        now = timezone.now()
        for service in queryset:
            if service.paid_until and service.paid_until > now:
                service.paid_until = service.paid_until + timedelta(days=7)
            else:
                service.paid_until = now + timedelta(days=7)
            service.status = 'active'
            service.is_active = True
            service.save()
        self.message_user(request, f'Продлено услуг: {queryset.count()} (на 7 дней)')
    
    @admin.action(description='Установить статус "Ожидает оплаты"')
    def mark_as_pending_payment(self, request, queryset):
        """Установка статуса ожидания оплаты"""
        updated = queryset.update(status='pending_payment', is_active=False, paid_until=None)
        self.message_user(request, f'Установлен статус ожидания оплаты для {updated} услуг')


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    """Админка для управления временными слотами"""
    
    list_display = ('service_link', 'date', 'start_time', 'end_time', 'is_booked_status', 'is_active_status')
    list_filter = ('date', 'is_booked', 'is_active', 'service', 'service__company')
    search_fields = ('service__name', 'service__company__name')
    readonly_fields = ('created_at',)
    ordering = ('date', 'start_time')
    date_hierarchy = 'date'
    
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
    
    actions = ['book_slots', 'unbook_slots', 'activate_slots', 'deactivate_slots']
    
    def service_link(self, obj):
        """Ссылка на услугу"""
        return format_html('<a href="{}">{}</a>', 
            f'/admin/services/service/{obj.service.id}/change/', 
            f"{obj.service.name} ({obj.service.company.name})"
        )
    service_link.short_description = _('Услуга')
    
    def is_booked_status(self, obj):
        """Статус бронирования"""
        if obj.is_booked:
            return format_html('<span style="color: red;">● Забронировано</span>')
        return format_html('<span style="color: green;">○ Свободно</span>')
    is_booked_status.short_description = _('Бронь')
    
    def is_active_status(self, obj):
        """Статус активности слота"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активен</span>')
        return format_html('<span style="color: gray;">✗ Не активен</span>')
    is_active_status.short_description = _('Статус')
    
    @admin.action(description='Забронировать выбранные слоты')
    def book_slots(self, request, queryset):
        """Бронирование слотов"""
        updated = queryset.update(is_booked=True)
        self.message_user(request, f'Забронировано слотов: {updated}')
    
    @admin.action(description='Освободить выбранные слоты')
    def unbook_slots(self, request, queryset):
        """Освобождение слотов"""
        updated = queryset.update(is_booked=False)
        self.message_user(request, f'Освобождено слотов: {updated}')
    
    @admin.action(description='Активировать выбранные слоты')
    def activate_slots(self, request, queryset):
        """Активация слотов"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано слотов: {updated}')
    
    @admin.action(description='Деактивировать выбранные слоты')
    def deactivate_slots(self, request, queryset):
        """Деактивация слотов"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано слотов: {updated}')
