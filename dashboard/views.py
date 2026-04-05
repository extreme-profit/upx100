from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Q
from accounts.models import User
from companies.models import Category
from services.models import Service


def home_view(request):
    """Главная страница сайта"""
    categories = Category.objects.all()[:6]
    services = Service.objects.select_related('provider').filter(is_active=True).order_by('-created_at')[:6]
    
    context = {
        'categories': categories,
        'services': services,
    }
    return render(request, 'home.html', context)


def is_admin(user):
    """Проверка на администратора"""
    return user.is_authenticated and (user.is_superuser or user.role == 'admin')


def admin_required(view_func):
    """Декоратор для ограничения доступа к админке"""
    return login_required(user_passes_test(is_admin)(view_func))


@admin_required
def dashboard_home(request):
    """Главная страница админ-панели"""
    # Статистика
    users_count = User.objects.count()
    entrepreneurs_count = User.objects.filter(role='entrepreneur').count()
    admins_count = User.objects.filter(role='admin').count()
    
    # Категории и подкатегории (импортируем здесь, чтобы избежать циклического импорта)
    from companies.models import Category, Subcategory
    categories_count = Category.objects.count()
    subcategories_count = Subcategory.objects.count()
    
    # Последние пользователи
    recent_users = User.objects.order_by('-date_joined')[:10]
    
    # Неактивные/заблокированные пользователи
    inactive_users = User.objects.filter(is_active=False).count()
    
    context = {
        'users_count': users_count,
        'entrepreneurs_count': entrepreneurs_count,
        'admins_count': admins_count,
        'categories_count': categories_count,
        'subcategories_count': subcategories_count,
        'recent_users': recent_users,
        'inactive_users': inactive_users,
        'title': 'Админ-панель',
    }
    return render(request, 'dashboard/home.html', context)


# ==================== КАТЕГОРИИ ====================

@admin_required
def category_list(request):
    """Список категорий"""
    from companies.models import Category
    categories = Category.objects.annotate(
        subcategories_count=Count('subcategories'),
    ).order_by('name')
    
    query = request.GET.get('q', '')
    if query:
        categories = categories.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    
    context = {
        'categories': categories,
        'query': query,
        'title': 'Категории услуг',
    }
    return render(request, 'dashboard/categories/list.html', context)


@admin_required
def category_create(request):
    """Создание категории"""
    from companies.models import Category
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        
        if not name:
            messages.error(request, 'Название категории обязательно')
            return redirect('dashboard:category_create')
        
        if not slug:
            slug = name.lower().replace(' ', '-').replace('--', '-')
        
        if Category.objects.filter(slug=slug).exists():
            messages.error(request, 'Категория с таким слагом уже существует')
            return redirect('dashboard:category_create')
        
        icon = request.FILES.get('icon')
        
        Category.objects.create(
            name=name,
            slug=slug,
            icon=icon if icon else None
        )
        
        messages.success(request, f'Категория "{name}" успешно создана')
        return redirect('dashboard:category_list')
    
    return render(request, 'dashboard/categories/form.html', {'title': 'Новая категория'})


@admin_required
def category_edit(request, pk):
    """Редактирование категории"""
    from companies.models import Category
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        
        if not name:
            messages.error(request, 'Название категории обязательно')
            return redirect('dashboard:category_edit', pk=pk)
        
        if not slug:
            slug = name.lower().replace(' ', '-').replace('--', '-')
        
        # Проверка уникальности слага (исключая текущую категорию)
        if Category.objects.filter(slug=slug).exclude(pk=pk).exists():
            messages.error(request, 'Категория с таким слагом уже существует')
            return redirect('dashboard:category_edit', pk=pk)
        
        category.name = name
        category.slug = slug
        
        if 'clear_icon' in request.POST:
            category.icon = None
        elif 'icon' in request.FILES:
            category.icon = request.FILES['icon']
        
        category.save()
        
        messages.success(request, f'Категория "{name}" успешно обновлена')
        return redirect('dashboard:category_list')
    
    context = {
        'category': category,
        'title': f'Редактирование: {category.name}',
    }
    return render(request, 'dashboard/categories/form.html', context)


@admin_required
def category_delete(request, pk):
    """Удаление категории"""
    from companies.models import Category
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Категория "{category_name}" успешно удалена')
        return redirect('dashboard:category_list')
    
    context = {
        'category': category,
        'title': f'Удаление: {category.name}',
    }
    return render(request, 'dashboard/categories/delete.html', context)


# ==================== ПОДКАТЕГОРИИ ====================

@admin_required
def subcategory_list(request):
    """Список подкатегорий"""
    from companies.models import Category, Subcategory
    subcategories = Subcategory.objects.select_related('category').order_by('category__name', 'name')
    
    category_filter = request.GET.get('category', '')
    if category_filter:
        subcategories = subcategories.filter(category_id=category_filter)
    
    query = request.GET.get('q', '')
    if query:
        subcategories = subcategories.filter(
            Q(name__icontains=query) | Q(category__name__icontains=query)
        )
    
    categories = Category.objects.all()
    
    context = {
        'subcategories': subcategories,
        'categories': categories,
        'selected_category': category_filter,
        'query': query,
        'title': 'Подкатегории услуг',
    }
    return render(request, 'dashboard/subcategories/list.html', context)


@admin_required
def subcategory_create(request):
    """Создание подкатегории"""
    from companies.models import Category, Subcategory
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        
        if not category_id:
            messages.error(request, 'Выберите категорию')
            return redirect('dashboard:subcategory_create')
        
        if not name:
            messages.error(request, 'Название подкатегории обязательно')
            return redirect('dashboard:subcategory_create')
        
        if not slug:
            slug = name.lower().replace(' ', '-').replace('--', '-')
        
        category = get_object_or_404(Category, pk=category_id)
        
        if Subcategory.objects.filter(slug=slug).exists():
            messages.error(request, 'Подкатегория с таким слагом уже существует')
            return redirect('dashboard:subcategory_create')
        
        Subcategory.objects.create(
            category=category,
            name=name,
            slug=slug
        )
        
        messages.success(request, f'Подкатегория "{name}" успешно создана')
        return redirect('dashboard:subcategory_list')
    
    categories = Category.objects.all()
    context = {
        'categories': categories,
        'title': 'Новая подкатегория',
    }
    return render(request, 'dashboard/subcategories/form.html', context)


@admin_required
def subcategory_edit(request, pk):
    """Редактирование подкатегории"""
    from companies.models import Category, Subcategory
    subcategory = get_object_or_404(Subcategory, pk=pk)
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        
        if not category_id:
            messages.error(request, 'Выберите категорию')
            return redirect('dashboard:subcategory_edit', pk=pk)
        
        if not name:
            messages.error(request, 'Название подкатегории обязательно')
            return redirect('dashboard:subcategory_edit', pk=pk)
        
        if not slug:
            slug = name.lower().replace(' ', '-').replace('--', '-')
        
        category = get_object_or_404(Category, pk=category_id)
        
        # Проверка уникальности слага (исключая текущую подкатегорию)
        if Subcategory.objects.filter(slug=slug).exclude(pk=pk).exists():
            messages.error(request, 'Подкатегория с таким слагом уже существует')
            return redirect('dashboard:subcategory_edit', pk=pk)
        
        subcategory.category = category
        subcategory.name = name
        subcategory.slug = slug
        subcategory.save()
        
        messages.success(request, f'Подкатегория "{name}" успешно обновлена')
        return redirect('dashboard:subcategory_list')
    
    categories = Category.objects.all()
    context = {
        'subcategory': subcategory,
        'categories': categories,
        'title': f'Редактирование: {subcategory.name}',
    }
    return render(request, 'dashboard/subcategories/form.html', context)


@admin_required
def subcategory_delete(request, pk):
    """Удаление подкатегории"""
    from companies.models import Subcategory
    subcategory = get_object_or_404(Subcategory, pk=pk)
    
    if request.method == 'POST':
        subcategory_name = subcategory.name
        subcategory.delete()
        messages.success(request, f'Подкатегория "{subcategory_name}" успешно удалена')
        return redirect('dashboard:subcategory_list')
    
    context = {
        'subcategory': subcategory,
        'title': f'Удаление: {subcategory.name}',
    }
    return render(request, 'dashboard/subcategories/delete.html', context)


# ==================== ПОЛЬЗОВАТЕЛИ ====================

@admin_required
def user_list(request):
    """Список пользователей"""
    users = User.objects.order_by('-date_joined')
    
    # Фильтры
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    query = request.GET.get('q', '')
    
    if role_filter:
        users = users.filter(role=role_filter)
    
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    if query:
        users = users.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(company_name__icontains=query)
        )
    
    context = {
        'users': users,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'query': query,
        'title': 'Пользователи / Компании',
    }
    return render(request, 'dashboard/users/list.html', context)


@admin_required
def user_detail(request, pk):
    """Детальная информация о пользователе"""
    user = get_object_or_404(User, pk=pk)
    
    context = {
        'user_obj': user,
        'title': f'{user.email} ({user.company_name or "Без названия"})',
    }
    return render(request, 'dashboard/users/detail.html', context)


@admin_required
def user_edit(request, pk):
    """Редактирование пользователя (смена роли, бан)"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        role = request.POST.get('role')
        is_active = request.POST.get('is_active') == 'on'
        
        if role and role in dict(User.ROLE_CHOICES):
            user.role = role
        
        user.is_active = is_active
        user.save()
        
        display_name = user.company_name or user.email
        messages.success(request, f'Пользователь "{display_name}" успешно обновлён')
        return redirect('dashboard:user_list')
    
    context = {
        'user_obj': user,
        'title': f'Редактирование: {user.email}',
    }
    return render(request, 'dashboard/users/edit.html', context)


@admin_required
def user_toggle_active(request, pk):
    """Бан/разбан пользователя (AJAX endpoint)"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()
        
        display_name = user.company_name or user.email
        status = 'разбанен' if user.is_active else 'забанен'
        messages.success(request, f'Пользователь "{display_name}" успешно {status}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'is_active': user.is_active})
        
        return redirect('dashboard:user_list')
    
    return redirect('dashboard:user_list')


@admin_required
def user_change_role(request, pk):
    """Смена роли пользователя (AJAX endpoint)"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        new_role = request.POST.get('role')
        
        if new_role and new_role in dict(User.ROLE_CHOICES):
            old_role = user.get_role_display()
            user.role = new_role
            user.save()
            
            display_name = user.company_name or user.email
            messages.success(request, f'Роль пользователя "{display_name}" изменена с "{old_role}" на "{user.get_role_display()}"')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'success': True, 'new_role': user.get_role_display()})
        
        return redirect('dashboard:user_list')
    
    return redirect('dashboard:user_list')

