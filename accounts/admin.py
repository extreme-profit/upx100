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
        count = Company.objects.filter(owner__in=queryset.filter(role='entrepreneur'), fraud_blocked=False).update(is_blocked=False)
        self.message_user(request, f'Разблокировано предпринимателей: {count}.')


from .models import FraudBlock, FraudIdentifier, SecurityEvent


class ReadOnlySecurityAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FraudBlock)
class FraudBlockAdmin(ReadOnlySecurityAdmin):
    list_display = ['id','company','confirmed_by','created_at','block_ips','lifted_at']
    list_filter = ['block_ips','lifted_at']
    search_fields = ['company__name','company__owner__email','reason']


@admin.register(FraudIdentifier)
class FraudIdentifierAdmin(ReadOnlySecurityAdmin):
    list_display = ['block','kind','value']
    list_filter = ['kind']
    search_fields = ['value']


@admin.register(SecurityEvent)
class SecurityEventAdmin(ReadOnlySecurityAdmin):
    list_display = ['created_at','action','email','phone','ip','matched_block']
    list_filter = ['action']
    search_fields = ['email','phone','company_phone','ip']
