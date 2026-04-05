from django.db import models
from django.conf import settings
from services.models import Service


class Payment(models.Model):
    """Платёж предпринимателя за услугу"""
    
    STATUS_CHOICES = (
        ('pending', 'Ожидает оплаты'),
        ('success', 'Успешно'),
        ('failed', 'Неудачно'),
        ('refunded', 'Возвращён'),
    )
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name='Услуга'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00,
        verbose_name='Сумма'
    )
    currency = models.CharField(
        max_length=3,
        default='RUB',
        verbose_name='Валюта'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        verbose_name='ID платежа в платёжной системе'
    )
    payment_url = models.URLField(
        blank=True,
        null=True,
        verbose_name='Ссылка на оплату'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание платежа'
    )
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Дата оплаты'
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
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['service', 'status']),
        ]
    
    def __str__(self):
        return f"Платёж {self.amount} {self.currency} для {self.service.name} ({self.get_status_display()})"
    
    def mark_as_paid(self, payment_id=None):
        """Отметить платёж как успешный"""
        from django.utils import timezone
        from datetime import timedelta
        
        self.status = 'success'
        self.paid_at = timezone.now()
        if payment_id:
            self.payment_id = payment_id
        
        # Активируем услугу на 30 дней
        service = self.service
        service.status = 'active'
        service.is_active = True
        service.paid_until = timezone.now() + timedelta(days=30)
        service.save()
        
        self.save()
