from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Company(models.Model):
    """Модель компании (предпринимателя)"""
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company')
    name = models.CharField(max_length=200, verbose_name="Название компании")
    description = models.TextField(blank=True, verbose_name="Описание")
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True, verbose_name="Логотип")
    photo = models.ImageField(upload_to='company_photos/', blank=True, null=True, verbose_name="Фото компании")
    address = models.CharField(max_length=300, verbose_name="Адрес")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="Широта")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="Долгота")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
    
    def __str__(self):
        return self.name


class Employee(models.Model):
    """Модель сотрудника компании"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees', verbose_name="Компания")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_profile')
    name = models.CharField(max_length=150, verbose_name="Имя сотрудника")
    position = models.CharField(max_length=100, blank=True, verbose_name="Должность")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    password = models.CharField(max_length=128, blank=True, verbose_name="Пароль для ЛК")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        unique_together = ['company', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"
    
    def set_password(self, raw_password):
        """Хеширование пароля"""
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)
        self.save()
    
    def check_password(self, raw_password):
        """Проверка пароля"""
        from django.contrib.auth.hashers import check_password
        if not self.password:
            return False
        return check_password(raw_password, self.password)


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
    """Модель услуги"""
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('active', 'Активна'),
        ('inactive', 'Неактивна (неоплата)'),
        ('pending_payment', 'Ожидает оплаты'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='services', verbose_name="Компания")
    category = models.ForeignKey('companies.Category', on_delete=models.SET_NULL, null=True, blank=True, 
                                  related_name='business_services', verbose_name="Категория")
    subcategory = models.ForeignKey('companies.Subcategory', on_delete=models.SET_NULL, null=True, blank=True, 
                                  related_name='business_services', verbose_name="Подкатегория")
    employees = models.ManyToManyField(Employee, related_name='services', verbose_name="Сотрудники")
    name = models.CharField(max_length=200, verbose_name="Название услуги")
    description = models.TextField(blank=True, verbose_name="Описание")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена (руб)")
    duration = models.PositiveIntegerField(help_text="Длительность в минутах", verbose_name="Длительность (мин)", null=True, blank=True)
    photo = models.ImageField(upload_to='service_photos/', blank=True, null=True, verbose_name="Фото услуги")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Поля для оплаты
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Сумма оплаты (руб/мес)")
    payment_due_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата окончания оплаты")
    last_payment_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата последней оплаты")
    
    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"
    
    def is_paid(self):
        """Проверка активности оплаты"""
        if self.status == 'active' and self.payment_due_date:
            return timezone.now() < self.payment_due_date
        return False
    
    def deactivate_if_unpaid(self):
        """Деактивация услуги при неуплате"""
        if self.payment_due_date and timezone.now() > self.payment_due_date + timedelta(days=30):
            self.status = 'inactive'
            self.save()
            return True
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
    """Бронирование услуги клиентом"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждено'),
        ('cancelled', 'Отменено'),
        ('completed', 'Выполнено'),
    ]
    
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='bookings', verbose_name="Услуга")
    client_name = models.CharField(max_length=150, verbose_name="Имя клиента")
    client_phone = models.CharField(max_length=20, verbose_name="Телефон клиента")
    client_email = models.EmailField(blank=True, verbose_name="Email клиента")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, verbose_name="Комментарий клиента")
    
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
        
        # Обновляем услугу
        service = self.service
        service.last_payment_date = self.payment_date
        service.payment_due_date = self.payment_date + timedelta(days=30)  # Оплата на месяц
        service.status = 'active'
        service.save()
