from django.contrib import admin
from .models import Category, Subcategory, Company, Employee


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'slug', 'created_at')
    list_filter = ('category',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('category', 'name')


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'address', 'is_verified', 'created_at')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('name', 'owner__username', 'email')
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
            'fields': ('latitude', 'longitude')
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


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'position', 'is_active', 'created_at')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'position')
    ordering = ('company', 'name')
