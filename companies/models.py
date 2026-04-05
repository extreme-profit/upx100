from django.db import models
from django.conf import settings


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


class Company(models.Model):
    """Профиль компании предпринимателя"""
    
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company',
        verbose_name='Владелец'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='Название компании'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    logo = models.ImageField(
        upload_to='companies/logos/',
        blank=True,
        null=True,
        verbose_name='Логотип'
    )
    photo = models.ImageField(
        upload_to='companies/photos/',
        blank=True,
        null=True,
        verbose_name='Фото компании'
    )
    address = models.CharField(
        max_length=300,
        verbose_name='Адрес'
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name='Широта'
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        verbose_name='Долгота'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Телефон'
    )
    email = models.EmailField(
        blank=True,
        verbose_name='Email'
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name='Проверена'
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
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class Employee(models.Model):
    """Профиль сотрудника компании"""
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='employees',
        verbose_name='Компания'
    )
    name = models.CharField(
        max_length=150,
        verbose_name='Имя сотрудника'
    )
    position = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Должность'
    )
    photo = models.ImageField(
        upload_to='employees/photos/',
        blank=True,
        null=True,
        verbose_name='Фото'
    )
    bio = models.TextField(
        blank=True,
        verbose_name='О себе'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    
    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['company', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"
