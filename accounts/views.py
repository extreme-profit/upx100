from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from business.models import Company


def get_login_redirect_url(user):
    """Определяет URL для перенаправления после входа в зависимости от роли"""
    if user.is_superuser or user.role == 'admin':
        return 'dashboard:home'
    elif user.role == 'entrepreneur':
        # Для предпринимателей - переход в личный кабинет компании
        return 'business:company_profile'
    elif user.role == 'employee':
        # Для сотрудников - переход в панель сотрудника (услуги и бронирования)
        return 'business:employee_dashboard'
    else:
        return 'home'


def register_company_view(request):
    """Страница регистрации компании"""
    if request.user.is_authenticated:
        return redirect(get_login_redirect_url(request.user))
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        company_name = request.POST.get('company_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        # Валидация
        if not email or not password:
            messages.error(request, 'Email и пароль обязательны')
            return render(request, 'accounts/register.html')
        
        if password != password_confirm:
            messages.error(request, 'Пароли не совпадают')
            return render(request, 'accounts/register.html')
        
        if len(password) < 8:
            messages.error(request, 'Пароль должен быть не менее 8 символов')
            return render(request, 'accounts/register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Пользователь с таким email уже существует')
            return render(request, 'accounts/register.html')
        
        if not company_name:
            messages.error(request, 'Название компании обязательно')
            return render(request, 'accounts/register.html')
        
        # Создание пользователя-предпринимателя со статусом "не проверен"
        user = User.objects.create_user(
            email=email,
            password=password,
            role='entrepreneur',
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_verified=False,  # По умолчанию компания не проверена
            is_active=True,
        )
        
        # Создаём связанную компанию с полными данными
        address = request.POST.get('address', '').strip()
        description = request.POST.get('description', '').strip()
        latitude = request.POST.get('latitude', '').strip() or None
        longitude = request.POST.get('longitude', '').strip() or None
        
        Company.objects.create(
            owner=user,
            name=company_name,
            phone=phone,
            email=email,
            address=address,
            description=description,
            latitude=latitude if latitude else None,
            longitude=longitude if longitude else None,
            is_verified=False,  # Компания не проверена до модерации
        )
        
        messages.success(request, f'Компания "{company_name}" успешно зарегистрирована! Ожидайте проверки администратором.')
        login(request, user)
        return redirect('business:company_profile')
    
    return render(request, 'accounts/register.html')


def login_view(request):
    """Страница входа"""
    if request.user.is_authenticated:
        return redirect(get_login_redirect_url(request.user))
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        
        if not email or not password:
            messages.error(request, 'Введите email и пароль')
            return render(request, 'accounts/login.html')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.email}!')
            return redirect(get_login_redirect_url(user))
        else:
            messages.error(request, 'Неверный email или пароль')
    
    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    """Выход из системы"""
    logout(request)
    messages.info(request, 'Вы вышли из системы')
    return redirect('dashboard:home')
