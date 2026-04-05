from django.db import models
from django.conf import settings
from companies.models import Subcategory


class Service(models.Model):
    """Услуга с окнами времени для записи"""
    
    STATUS_CHOICES = (
        ('pending_payment', 'Ожидает оплаты'),
        ('active', 'Активна'),
        ('inactive', 'Неактивна'),
        ('expired', 'Истекла'),
    )
    
    # Предприниматель == пользователь с ролью entrepreneur
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='services',
        limit_choices_to={'role': 'entrepreneur'},
        verbose_name='Предприниматель'
    )
    employee_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Имя сотрудника (опционально)'
    )
    subcategory = models.ForeignKey(
        Subcategory,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='services',
        verbose_name='Подкатегория'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='Название услуги'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена'
    )
    duration_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name='Длительность (минуты)'
    )
    photo = models.ImageField(
        upload_to='services/photos/',
        blank=True,
        null=True,
        verbose_name='Фото услуги'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending_payment',
        verbose_name='Статус'
    )
    paid_until = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Оплачено до'
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Активна'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Поля для векторного поиска (будут заполняться через Celery)
    embedding = models.BinaryField(
        blank=True,
        null=True,
        editable=True,
        verbose_name='Векторное представление'
    )
    
    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['provider', 'status']),
        ]
    
    def __str__(self):
        company_name = self.provider.company_name if self.provider.company_name else self.provider.email
        return f"{self.name} ({company_name})"
    
    @property
    def is_paid(self):
        """Проверка активности оплаты"""
        if not self.paid_until:
            return False
        from django.utils import timezone
        return timezone.now() < self.paid_until


class TimeSlot(models.Model):
    """Окно времени для записи на услугу"""
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name='Услуга'
    )
    date = models.DateField(
        verbose_name='Дата'
    )
    start_time = models.TimeField(
        verbose_name='Начало'
    )
    end_time = models.TimeField(
        verbose_name='Конец'
    )
    is_booked = models.BooleanField(
        default=False,
        verbose_name='Забронировано'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активно'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    
    class Meta:
        verbose_name = 'Временной слот'
        verbose_name_plural = 'Временные слоты'
        ordering = ['date', 'start_time']
        unique_together = [['service', 'date', 'start_time']]
        indexes = [
            models.Index(fields=['date', 'is_booked']),
            models.Index(fields=['service', 'date']),
        ]
    
    def __str__(self):
        return f"{self.service.name} - {self.date} {self.start_time}"

