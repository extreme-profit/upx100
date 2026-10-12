from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'phone']
    ordering = ['email']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('date_joined', 'last_login')}),
    )
    readonly_fields = ['date_joined', 'last_login']
    actions = ['block_entrepreneurs', 'unblock_entrepreneurs']

    @admin.action(description='Заблокировать предпринимателей и скрыть все их услуги')
    def block_entrepreneurs(self, request, queryset):
        from business.models import Company
        count = Company.objects.filter(owner__in=queryset.filter(role='entrepreneur')).update(is_blocked=True)
        self.message_user(request, f'Заблокировано предпринимателей: {count}. Все их услуги скрыты.')

    @admin.action(description='Разблокировать предпринимателей')
    def unblock_entrepreneurs(self, request, queryset):
        from business.models import Company
        count = Company.objects.filter(owner__in=queryset.filter(role='entrepreneur')).update(is_blocked=False)
        self.message_user(request, f'Разблокировано предпринимателей: {count}.')
