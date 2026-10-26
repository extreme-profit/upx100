from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        
        # Админ всегда активен
        extra_fields['is_active'] = True
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('admin', 'Администратор'),
        ('entrepreneur', 'Предприниматель'),
        ('employee', 'Сотрудник'),
    )

    email = models.EmailField('Email', unique=True)
    first_name = models.CharField('Имя', max_length=30, blank=True)
    last_name = models.CharField('Фамилия', max_length=30, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    
    # Роль определяет доступ
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES, default='entrepreneur')
    
    # Стандартные флаги Django
    is_staff = models.BooleanField('Статус сотрудника', default=False)
    is_active = models.BooleanField('Активен', default=True)
    date_joined = models.DateTimeField('Дата регистрации', default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        role_label = dict(self.ROLE_CHOICES).get(self.role, self.role)
        return f"{self.email} [{role_label}]"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def is_entrepreneur(self):
        return self.role == 'entrepreneur'
    
    def is_employee(self):
        return self.role == 'employee'
    
    def get_employee_profile(self):
        """Возвращает профиль сотрудника, если пользователь - сотрудник"""
        if hasattr(self, 'employee_profile'):
            return self.employee_profile
        return None
    
    def get_company(self):
        """Возвращает компанию пользователя (для предпринимателя или сотрудника)"""
        from business.models import Company
        if self.role == 'entrepreneur':
            # Компания предпринимателя связана через company.owner
            try:
                return self.company
            except Company.DoesNotExist:
                return None
        elif self.role == 'employee':
            employee_profile = self.get_employee_profile()
            if employee_profile:
                return employee_profile.company
        return None


class FraudBlock(models.Model):
    company = models.ForeignKey('business.Company', on_delete=models.PROTECT, related_name='fraud_blocks')
    confirmed_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='confirmed_fraud_blocks')
    reason = models.TextField(max_length=4000)
    evidence = models.TextField(max_length=10000, blank=True)
    snapshot = models.JSONField(default=dict)
    block_ips = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='lifted_fraud_blocks')
    lift_reason = models.TextField(max_length=4000, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['company'], condition=models.Q(lifted_at__isnull=True), name='unique_active_company_fraud_block')]
        verbose_name = 'Подтверждённая антифрод-блокировка'
        verbose_name_plural = 'Подтверждённые антифрод-блокировки'


class FraudIdentifier(models.Model):
    block = models.ForeignKey(FraudBlock, on_delete=models.PROTECT, related_name='identifiers')
    kind = models.CharField(max_length=8, choices=[('phone', 'Телефон'), ('ip', 'IP')])
    value = models.CharField(max_length=64, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['block', 'kind', 'value'], name='unique_fraud_block_identifier')]


class SecurityEvent(models.Model):
    ACTIONS = [('registered', 'Регистрация'), ('registration_blocked', 'Повторная регистрация заблокирована'),
               ('login', 'Вход'), ('service_saved', 'Услуга сохранена'), ('service_blocked', 'Создание услуги запрещено'),
               ('profile_saved', 'Профиль сохранён')]
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='security_events')
    company = models.ForeignKey('business.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='security_events')
    matched_block = models.ForeignKey(FraudBlock, on_delete=models.PROTECT, null=True, blank=True, related_name='events')
    action = models.CharField(max_length=24, choices=ACTIONS, db_index=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    company_phone = models.CharField(max_length=32, blank=True, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Событие безопасности предпринимателя'
        verbose_name_plural = 'События безопасности предпринимателей'
