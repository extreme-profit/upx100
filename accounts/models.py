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
