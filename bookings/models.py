from django.db import models
from django.conf import settings
from services.models import Service, TimeSlot


class Booking(models.Model):
    """Заявка на запись клиента на услугу"""
    
    STATUS_CHOICES = (
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждена'),
        ('cancelled', 'Отменена'),
        ('completed', 'Выполнена'),
        ('no_show', 'Не явился'),
    )
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name='Услуга'
    )
    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='bookings',
        verbose_name='Временной слот'
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name='Клиент'
    )
    client_name = models.CharField(
        max_length=150,
        verbose_name='Имя клиента'
    )
    client_email = models.EmailField(
        verbose_name='Email клиента'
    )
    client_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Телефон клиента'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Примечание'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    confirmed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Дата подтверждения'
    )
    
    class Meta:
        verbose_name = 'Заявка на запись'
        verbose_name_plural = 'Заявки на запись'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['service', 'status']),
            models.Index(fields=['client', 'status']),
        ]
    
    def __str__(self):
        return f"{self.client_name} -> {self.service.name} ({self.get_status_display()})"
    
    def confirm_booking(self):
        """Подтверждение заявки"""
        from django.utils import timezone
        self.status = 'confirmed'
        self.confirmed_at = timezone.now()
        self.save()
        if self.time_slot:
            self.time_slot.is_booked = True
            self.time_slot.save()
    
    def cancel_booking(self):
        """Отмена заявки"""
        self.status = 'cancelled'
        self.save()
        if self.time_slot:
            self.time_slot.is_booked = False
            self.time_slot.save()
