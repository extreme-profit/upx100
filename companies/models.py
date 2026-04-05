from django.db import models


class Category(models.Model):
    """Глобальная категория услуг (Красота, Авто, Ремонт и т.д.)"""
    
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Название категории'
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='Слаг'
    )
    icon = models.ImageField(
        upload_to='categories/icons/',
        blank=True,
        null=True,
        verbose_name='Иконка'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_subcategories_count(self):
        """Количество подкатегорий"""
        return self.subcategories.count()
    
    def get_services_count(self):
        """Количество услуг во всех подкатегориях"""
        from services.models import Service
        return Service.objects.filter(subcategory__category=self).count()


class Subcategory(models.Model):
    """Подкатегория услуг (привязка к глобальной категории)"""
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name='Категория'
    )
    name = models.CharField(
        max_length=100,
        verbose_name='Название подкатегории'
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='Слаг'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    
    class Meta:
        verbose_name = 'Подкатегория'
        verbose_name_plural = 'Подкатегории'
        ordering = ['category', 'name']
        unique_together = [['category', 'slug']]
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"
    
    def get_services_count(self):
        """Количество услуг в подкатегории"""
        from services.models import Service
        return Service.objects.filter(subcategory=self).count()

