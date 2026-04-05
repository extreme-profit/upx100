from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Админка для управления пользователями с расширенными функциями"""
    
    list_display = ('username', 'email', 'role', 'phone', 'is_active_status', 'created_at', 'quick_actions')
    list_filter = ('role', 'is_active', 'is_staff', 'created_at')
    search_fields = ('username', 'email', 'phone', 'first_name', 'last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'last_login')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Профиль', {
            'fields': ('role', 'phone', 'avatar'),
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительно', {
            'fields': ('role', 'phone'),
        }),
    )
    
    actions = ['ban_users', 'unban_users', 'make_client', 'make_entrepreneur', 'make_admin']
    
    def is_active_status(self, obj):
        """Статус активности пользователя с цветовой индикацией"""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активен</span>')
        return format_html('<span style="color: red;">✗ Заблокирован</span>')
    is_active_status.short_description = _('Статус')
    
    def quick_actions(self, obj):
        """Быстрые действия для пользователя"""
        if obj.is_active:
            url = reverse('admin:accounts_user_changelist')
            return format_html(
                '<a href="{}?q={}" style="color: red;">Заблокировать</a>',
                url, obj.username
            )
        return format_html(
            '<a href="{}?q={}" style="color: green;">Разблокировать</a>',
            reverse('admin:accounts_user_changelist'), obj.username
        )
    quick_actions.short_description = _('Действия')
    
    @admin.action(description='Заблокировать выбранных пользователей')
    def ban_users(self, request, queryset):
        """Бан выбранных пользователей"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Заблокировано пользователей: {updated}')
    
    @admin.action(description='Разблокировать выбранных пользователей')
    def unban_users(self, request, queryset):
        """Разблокировка выбранных пользователей"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Разблокировано пользователей: {updated}')
    
    @admin.action(description='Установить роль: Клиент')
    def make_client(self, request, queryset):
        """Смена роли на клиента"""
        updated = queryset.update(role='client')
        self.message_user(request, f'Роль изменена для {updated} пользователей')
    
    @admin.action(description='Установить роль: Предприниматель')
    def make_entrepreneur(self, request, queryset):
        """Смена роли на предпринимателя"""
        updated = queryset.update(role='entrepreneur')
        self.message_user(request, f'Роль изменена для {updated} пользователей')
    
    @admin.action(description='Установить роль: Администратор')
    def make_admin(self, request, queryset):
        """Смена роли на администратора"""
        updated = queryset.update(role='admin')
        self.message_user(request, f'Роль изменена для {updated} пользователей')
