from django.db import models


class SearchQuery(models.Model):
    """История поисковых запросов для аналитики"""
    
    query = models.CharField(
        max_length=300,
        verbose_name='Поисковый запрос'
    )
    results_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Количество результатов'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата поиска'
    )
    user_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name='IP пользователя'
    )
    
    class Meta:
        verbose_name = 'Поисковый запрос'
        verbose_name_plural = 'Поисковые запросы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.query} ({self.results_count} результатов)"


class StaticPage(models.Model):
    """Статические страницы (О нас, Контакты и т.д.)"""
    
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='Слаг'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Заголовок'
    )
    content = models.TextField(
        verbose_name='Контент'
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name='Опубликовано'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        verbose_name = 'Статическая страница'
        verbose_name_plural = 'Статические страницы'
        ordering = ['title']
    
    def __str__(self):
        return self.title
