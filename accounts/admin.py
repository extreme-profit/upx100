from django.contrib import admin
from .models import User

# Стандартная админка отключена, так как используется кастомный дашборд /dashboard
# Чтобы избежать ошибок при проверке системы (SystemCheckError), регистрируем минимальную конфигурацию

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'company_name', 'role', 'is_active', 'is_verified']
    list_filter = ['role', 'is_active', 'is_verified']
    search_fields = ['email', 'company_name']
    ordering = ['email']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Company Info', {'fields': ('company_name', 'company_description', 'company_logo', 'company_address', 'latitude', 'longitude', 'is_verified')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login',)}),
    )
    readonly_fields = ['last_login']
