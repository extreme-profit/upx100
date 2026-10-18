import uuid
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo
from .timezones import timezone_choices

class Company(models.Model):
    """Модель компании (предпринимателя)"""
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company')
    time_zone = models.CharField(max_length=64, default="Europe/Moscow", choices=timezone_choices, verbose_name="Часовой пояс")
    name = models.CharField(max_length=200, verbose_name="Название компании")
    description = models.TextField(blank=True, verbose_name="Описание")
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True, verbose_name="Логотип")
    photo = models.ImageField(upload_to='company_photos/', blank=True, null=True, verbose_name="Фото компании")
    city = models.CharField(max_length=150, blank=True, db_index=True, verbose_name="Город")
    address = models.CharField(max_length=300, verbose_name="Адрес")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="Широта")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="Долгота")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    is_verified = models.BooleanField(default=False, verbose_name="Проверена модератором")
    is_blocked = models.BooleanField(default=False, verbose_name="Услуги предпринимателя заблокированы")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def tzinfo(self):
        return ZoneInfo(self.time_zone)

    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
    
    def __str__(self):
        return self.name


class ServiceQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(
            is_archived=False, company__is_verified=True, company__is_blocked=False,
            company__owner__is_active=True,
        )


class Employee(models.Model):
    """Модель сотрудника компании
    
    Сотрудник теперь всегда связан с пользователем User с ролью 'employee'.
    Пользователь хранит данные для аутентификации, а Employee - профильные данные.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees', verbose_name="Компания")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee_profile')
    position = models.CharField(max_length=100, blank=True, verbose_name="Должность")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        unique_together = ['company', 'user']
    
    def __str__(self):
        return f"{self.user.get_full_name()} ({self.company.name})"
    
    @property
    def name(self):
        """Имя сотрудника из связанного пользователя"""
        return self.user.get_full_name() or self.user.email
    
    @property
    def email(self):
        """Email сотрудника из связанного пользователя"""
        return self.user.email


class ServiceCategory(models.Model):
    """Подкатегория услуг (для привязки услуг)"""
    name = models.CharField(max_length=100, verbose_name="Название подкатегории")
    slug = models.SlugField(unique=True, verbose_name="URL")
    
    class Meta:
        verbose_name = "Подкатегория услуг"
        verbose_name_plural = "Подкатегории услуг"
    
    def __str__(self):
        return self.name


class Service(models.Model):
    DELIVERY_CHOICES = [('remote', 'Удалённо'), ('onsite', 'На месте'), ('visit', 'Выезд')]
    delivery_mode = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default='onsite', verbose_name='Формат оказания услуги')
    """Модель услуги"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='services', verbose_name="Компания")
    category = models.ForeignKey('companies.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='business_services', verbose_name="Категория")
    subcategory = models.ForeignKey('companies.Subcategory', on_delete=models.SET_NULL, null=True, blank=True, related_name='business_services', verbose_name="Подкатегория")
    employees = models.ManyToManyField(Employee, related_name='services', verbose_name="Сотрудники")
    name = models.CharField(max_length=200, verbose_name="Название услуги")
    description = models.TextField(blank=True, verbose_name="Описание")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена (руб)")
    duration = models.PositiveIntegerField(help_text="Длительность в минутах", verbose_name="Длительность (мин)", null=True, blank=True)
    photo = models.ImageField(upload_to='service_photos/', blank=True, null=True, verbose_name="Фото услуги")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False, verbose_name="Архивная услуга")

    objects = ServiceQuerySet.as_manager()
    
    # Поля для оплаты
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Сумма оплаты (руб/мес)")
    payment_due_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата окончания оплаты")
    last_payment_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата последней оплаты")
    
    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"

    @property
    def status(self):
        if self.is_archived or self.company.is_blocked or not self.company.owner.is_active:
            return 'inactive'
        return 'active' if self.company.is_verified else 'pending_verification'

    @property
    def status_display(self):
        """Отображаемое название статуса"""
        status_map = {
            'pending_verification': 'Ожидает проверки компании',
            'active': 'Опубликована бесплатно',
            'inactive': 'Скрыта',
        }
        return status_map.get(self.status, self.status)

    def is_paid(self):
        """Историческая оплата не влияет на публикацию услуги."""
        return self.payments.filter(status='success').exists()
    
    def deactivate_if_unpaid(self):
        """Санкции применяет администратор к предпринимателю вручную."""
        return False


class ServiceTimeSlot(models.Model):
    """Временные слоты для записи на услугу"""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='time_slots', verbose_name="Услуга")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='time_slots', verbose_name="Сотрудник", null=True)
    date = models.DateField(verbose_name="Дата")
    start_time = models.TimeField(verbose_name="Время начала")
    end_time = models.TimeField(verbose_name="Время окончания")
    is_booked = models.BooleanField(default=False, verbose_name="Забронировано")
    booking = models.ForeignKey('Booking', on_delete=models.SET_NULL, null=True, blank=True, 
                                 related_name='time_slots', verbose_name="Бронирование")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"
        unique_together = ['service', 'employee', 'date', 'start_time']
        ordering = ['date', 'start_time']
    
    def __str__(self):
        return f"{self.service.name} - {self.employee.name if self.employee else 'Общий'} - {self.date} {self.start_time}"


class Booking(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings', editable=False)
    appointment_end_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    review_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    visitor_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    appointment_at = models.DateTimeField(null=True, blank=True, editable=False)
    """Бронирование услуги клиентом"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждено'),
        ('cancelled', 'Отклонено'),
        ('client_cancelled', 'Отменено клиентом'),
        ('completed', 'Выполнено'),
    ]
    
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='bookings', verbose_name="Услуга")
    client_name = models.CharField(max_length=150, verbose_name="Имя клиента")
    client_phone = models.CharField(max_length=20, verbose_name="Телефон клиента")
    client_email = models.EmailField(blank=True, verbose_name="Email клиента")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, verbose_name="Комментарий клиента")
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Первое подтверждение")
    
    class Meta:
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.client_name} - {self.service.name} ({self.get_status_display()})"


class Payment(models.Model):
    """Модель оплаты услуги"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('success', 'Оплачено'),
        ('failed', 'Ошибка оплаты'),
        ('refunded', 'Возврат'),
    ]

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='payments', verbose_name="Услуга")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма (руб)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    payment_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата оплаты")
    transaction_id = models.CharField(max_length=100, blank=True, verbose_name="ID транзакции")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"
        ordering = ['-created_at']

    def __str__(self):
        return f"Платеж {self.amount} руб. для {self.service.name} ({self.get_status_display()})"

    def mark_as_paid(self):
        """Обработка успешной оплаты"""
        if self.status == 'success':
            return

        self.status = 'success'
        self.payment_date = timezone.now()
        self.save()

        # Старые платежи сохраняются для истории, публикация бесплатна.


class MonthlyInvoice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoices')
    period = models.DateField(verbose_name='Расчётный месяц')
    due_date = models.DateField(verbose_name='Оплатить до (включительно)')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=[('pending', 'Ожидает оплаты'), ('paid', 'Оплачен')], default='pending')
    gateway_reference = models.CharField(max_length=100, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period', '-pk']
        constraints = [models.UniqueConstraint(fields=['company', 'period'], name='unique_company_month_invoice')]
        verbose_name = 'Ежемесячный счёт'
        verbose_name_plural = 'Ежемесячные счета'

    def __str__(self):
        return f'{self.company.name}: {self.period:%m.%Y} — {self.amount} ₽'

    @property
    def is_overdue(self):
        return self.status == 'pending' and timezone.localdate() > self.due_date


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(MonthlyInvoice, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='invoice_items')
    service_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=100)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['invoice', 'service'], name='unique_invoice_service')]
        verbose_name = 'Услуга в счёте'
        verbose_name_plural = 'Услуги в счёте'


class EmailNotification(models.Model):
    """Сохранённые письма: ошибки SMTP можно повторить без потери заявки."""
    key = models.CharField(max_length=150, unique=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Почтовое уведомление'
        verbose_name_plural = 'Почтовые уведомления'


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name='review')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(check=models.Q(rating__gte=1, rating__lte=5), name='review_rating_1_to_5')]
        verbose_name = 'Отзыв о мастере'
        verbose_name_plural = 'Отзывы о мастерах'
