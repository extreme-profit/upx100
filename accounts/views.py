from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User


def get_login_redirect_url(user):
    """Определяет URL для перенаправления после входа в зависимости от роли"""
    if user.is_superuser or user.role == 'admin':
        return 'dashboard:home'
    elif user.role == 'entrepreneur':
        # Для предпринимателей можно создать отдельную страницу или перенаправлять на главную
        return 'home'  # или можно создать 'dashboard:entrepreneur_home' в будущем
    else:
        return 'home'


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
