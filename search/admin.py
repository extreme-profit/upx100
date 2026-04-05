from django.contrib import admin
from .models import SearchQuery, StaticPage


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ('query', 'results_count', 'user_ip', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('query',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('title',)
    
    fieldsets = (
        ('Основное', {
            'fields': ('title', 'slug', 'content')
        }),
        ('Публикация', {
            'fields': ('is_published',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
