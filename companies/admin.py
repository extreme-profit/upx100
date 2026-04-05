from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Category, Subcategory, Company, Employee


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Админка для управления глобальными категориями услуг"""
    
    list_display = ('name', 'slug', 'icon_preview', 'services_count', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)
    
    def icon_preview(self, obj):
        """Предпросмотр иконки категории"""
        if obj.icon:
            return format_html('<img src="{}" style="width: 30px; height: 30px; object-fit: contain;" />', obj.icon.url)
        return format_html('<span style="color: gray;">Нет иконки</span>')
    icon_preview.short_description = _('Иконка')
    
    def services_count(self, obj):
        """Количество услуг в категории"""
        from services.models import Service
        count = Service.objects.filter(subcategory__category=obj).count()
        return format_html('<b>{}</b>', count)
    services_count.short_description = _('Услуг')


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    """Админка для управления подкатегориями услуг"""
    
    list_display = ('name', 'category', 'slug', 'services_count', 'created_at')
    list_filter = ('category',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('category', 'name')
    
    def services_count(self, obj):
        """Количество услуг в подкатегории"""
        count = obj.services.count()
        return format_html('<b>{}</b>', count)
    services_count.short_description = _('Услуг')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Админка для управления компаниями предпринимателей"""
    
    list_display = ('name', 'owner', 'address', 'is_verified_status', 'employees_count', 'services_count', 'created_at')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('name', 'owner__username', 'email', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('owner', 'name', 'description')
        }),
        ('Контакты', {
            'fields': ('address', 'phone', 'email')
        }),
        ('Геолокация', {
            'fields': ('latitude', 'longitude'),
            'description': 'Координаты для поиска по локации'
        }),
        ('Медиа', {
            'fields': ('logo', 'photo')
        }),
        ('Статус', {
            'fields': ('is_verified',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['verify_companies', 'unverify_companies']
    
    def is_verified_status(self, obj):
        """Статус верификации компании"""
        if obj.is_verified:
            return format_html('<span style="color: green;">✓ Проверена</span>')
        return format_html('<span style="color: orange;">○ Не проверена</span>')
    is_verified_status.short_description = _('Статус')
    
    def employees_count(self, obj):
        """Количество сотрудников"""
        count = obj.employees.count()
        return format_html('<b>{}</b>', count)
    employees_count.short_description = _('Сотрудников')
    
    def services_count(self, obj):
        """Количество услуг компании"""
        count = obj.services.count()
        return format_html('<b>{}</b>', count)
    services_count.short_description = _('Услуг')
    
    @admin.action(description='Верифицировать выбранные компании')
    def verify_companies(self, request, queryset):
        """Верификация компаний"""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'Верифицировано компаний: {updated}')
    
    @admin.action(description='Снять верификацию с выбранных компаний')
    def unverify_companies(self, request, queryset):
        """Снятие верификации"""
        updated = queryset.update(is_verified=False)
        self.message_user(request, f'Снята верификация с {updated} компаний')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    """Админка для управления сотрудниками компаний"""
    
    list_display = ('name', 'company', 'position', 'photo_preview', 'is_active_status', 'services_count', 'created_at')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'position', 'company__name')
    ordering = ('company', 'name')
    
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'name', 'position')
        }),
        ('Информация', {
            'fields': ('bio', 'photo')
        }),
        ('Статус', {
            'fields': ('is_active',)
        }),
        ('Даты', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_employees', 'deactivate_employees']
    
    def photo_preview(self, obj):
        """Предпросмотр фото сотрудника"""
        if obj.photo:
            return format_html('<img src="{}" style="width: 30px; height: 30px; border-radius: 50%; object-fit: cover;" />', obj.photo.url)
        return format_html('<span style="color: gray;">Нет фото</span>')
    photo_preview.short_description = _('Фото')
    
    def is_active_status(self, obj):
        """Статус активности сотрудника"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активен</span>')
        return format_html('<span style="color: red;">✗ Не активен</span>')
    is_active_status.short_description = _('Статус')
    
    def services_count(self, obj):
        """Количество услуг сотрудника"""
        count = obj.services.count()
        return format_html('<b>{}</b>', count)
    services_count.short_description = _('Услуг')
    
    @admin.action(description='Активировать выбранных сотрудников')
    def activate_employees(self, request, queryset):
        """Активация сотрудников"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано сотрудников: {updated}')
    
    @admin.action(description='Деактивировать выбранных сотрудников')
    def deactivate_employees(self, request, queryset):
        """Деактивация сотрудников"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано сотрудников: {updated}')
