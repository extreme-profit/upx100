from django.contrib import admin
from .models import Company, Employee, ServiceCategory, Service, ServiceTimeSlot, Booking, Payment
from .models import MonthlyInvoice, InvoiceItem, EmailNotification


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'address', 'is_verified', 'is_blocked', 'created_at']
    search_fields = ['name', 'owner__email', 'address']
    readonly_fields = ['created_at', 'updated_at']
    list_filter = ['is_verified', 'is_blocked', 'city']
    actions = ['block_services', 'unblock_services']

    @admin.action(description='Скрыть все текущие и будущие услуги предпринимателей')
    def block_services(self, request, queryset):
        count = queryset.update(is_blocked=True)
        self.message_user(request, f'Услуги скрыты у {count} компаний.')

    @admin.action(description='Разблокировать услуги предпринимателей')
    def unblock_services(self, request, queryset):
        count = queryset.update(is_blocked=False)
        self.message_user(request, f'Услуги разблокированы у {count} компаний.')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'position', 'is_active', 'created_at']
    list_filter = ['company', 'is_active']
    search_fields = ['name', 'company__name']


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'category', 'get_employees_list', 'price', 'duration', 'status', 'payment_due_date']
    list_filter = ['company', 'category', 'delivery_mode']
    search_fields = ['name', 'company__name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['employees']
    
    def get_employees_list(self, obj):
        """Получение списка сотрудников через запятую"""
        return ", ".join([emp.name for emp in obj.employees.all()])
    get_employees_list.short_description = 'Сотрудники'


@admin.register(ServiceTimeSlot)
class ServiceTimeSlotAdmin(admin.ModelAdmin):
    list_display = ['service', 'date', 'start_time', 'end_time', 'is_booked']
    list_filter = ['date', 'is_booked', 'service']
    search_fields = ['service__name']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'service', 'status', 'created_at']
    list_filter = ['status', 'service']
    search_fields = ['client_name', 'client_phone', 'service__name']
    readonly_fields = ['created_at', 'updated_at', 'confirmed_at', 'status']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['service', 'amount', 'status', 'payment_date', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['service__name', 'transaction_id']
    readonly_fields = ['created_at']


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['service', 'service_name', 'amount']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MonthlyInvoice)
class MonthlyInvoiceAdmin(admin.ModelAdmin):
    list_display = ['company', 'period', 'amount', 'due_date', 'status', 'is_overdue']
    list_filter = ['status', 'period', 'due_date']
    search_fields = ['company__name', 'company__owner__email', 'gateway_reference']
    readonly_fields = ['company', 'period', 'amount', 'due_date', 'status', 'gateway_reference', 'paid_at', 'created_at']
    inlines = [InvoiceItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = ['subject', 'recipient', 'sent_at', 'attempts', 'last_error']
    list_filter = ['sent_at']
    readonly_fields = ['key', 'recipient', 'subject', 'body', 'created_at', 'sent_at', 'attempts', 'last_error']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from .models import Review

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['employee', 'rating', 'created_at']
    list_filter = ['rating', 'employee__company']
    readonly_fields = ['booking', 'employee', 'rating', 'comment', 'created_at']

    def has_add_permission(self, request):
        return False
