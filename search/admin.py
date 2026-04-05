from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import SearchQuery, StaticPage


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    """Админка для просмотра истории поисковых запросов (аналитика)"""
    
    list_display = ('query', 'results_count', 'user_ip', 'created_at_display')
    list_filter = ('created_at',)
    search_fields = ('query',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    def created_at_display(self, obj):
        """Дата поиска в удобном формате"""
        return obj.created_at.strftime('%d.%m.%Y %H:%M')
    created_at_display.short_description = _('Дата')


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    """Админка для управления статическими страницами (О нас, Контакты и т.д.)"""
    
    list_display = ('title', 'slug', 'is_published_status', 'content_preview', 'updated_at_display')
    list_filter = ('is_published',)
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('title',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('title', 'slug', 'content'),
            'description': 'Заголовок, слаг и контент страницы'
        }),
        ('Публикация', {
            'fields': ('is_published',),
            'description': 'Управление видимостью страницы'
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['publish_pages', 'unpublish_pages']
    
    def is_published_status(self, obj):
        """Статус публикации"""
        if obj.is_published:
            return format_html('<span style="color: green;">✓ Опубликована</span>')
        return format_html('<span style="color: orange;">○ Черновик</span>')
    is_published_status.short_description = _('Статус')
    
    def content_preview(self, obj):
        """Предпросмотр контента"""
        if obj.content:
            preview = obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
            return format_html('<span style="color: gray;">{}</span>', preview)
        return format_html('<span style="color: gray;">Пусто</span>')
    content_preview.short_description = _('Контент')
    
    def updated_at_display(self, obj):
        """Дата обновления в удобном формате"""
        return obj.updated_at.strftime('%d.%m.%Y %H:%M')
    updated_at_display.short_description = _('Обновлено')
    
    @admin.action(description='Опубликовать выбранные страницы')
    def publish_pages(self, request, queryset):
        """Публикация страниц"""
        updated = queryset.update(is_published=True)
        self.message_user(request, f'Опубликовано страниц: {updated}')
    
    @admin.action(description='Снять с публикации выбранные страницы')
    def unpublish_pages(self, request, queryset):
        """Снятие с публикации"""
        updated = queryset.update(is_published=False)
        self.message_user(request, f'Снято с публикации: {updated} страниц')
