from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Category, Subcategory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Админка для управления глобальными категориями услуг"""
    
    list_display = ('name', 'slug', 'icon_preview', 'subcategories_count', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)
    
    def icon_preview(self, obj):
        """Предпросмотр иконки категории"""
        if obj.icon:
            return format_html('<img src="{}" style="width: 30px; height: 30px; object-fit: contain;" />', obj.icon.url)
        return format_html('<span style="color: gray;">Нет иконки</span>')
    icon_preview.short_description = _('Иконка')
    
    def subcategories_count(self, obj):
        """Количество подкатегорий в категории"""
        count = obj.get_subcategories_count()
        return format_html('<b>{}</b>', count)
    subcategories_count.short_description = _('Подкатегорий')


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    """Админка для управления подкатегориями услуг"""
    
    list_display = ('name', 'category', 'slug', 'created_at')
    list_filter = ('category',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('category', 'name')

