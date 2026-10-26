from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Q, Sum
from accounts.models import User, SecurityEvent
from companies.models import Category
from business.models import Service, Company, MonthlyInvoice, Booking, NoShowReport
from datetime import datetime
from django.utils import timezone


def about_view(request):
    """Страница 'О нас'"""
    return render(request, 'about.html')


def cookie_policy_view(request):
    """Страница политики cookie"""
    context = {
        'now': datetime.now()
    }
    return render(request, 'cookie_policy.html', context)


def home_view(request):
    """Главная страница сайта"""
    categories = Category.objects.all()[:6]
    services = Service.objects.visible().select_related('company').filter(
        company__is_verified=True
    ).order_by('-created_at')[:6]

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
        'blocked_registration_count': SecurityEvent.objects.filter(action='registration_blocked').count(),
        'invoices_total': MonthlyInvoice.objects.exclude(status='void').count(),
        'invoices_paid': MonthlyInvoice.objects.filter(status='paid').count(),
        'invoices_paid_amount': MonthlyInvoice.objects.filter(status='paid').aggregate(total=Sum('amount'))['total'] or 0,
        'active_entrepreneurs': User.objects.filter(role='entrepreneur', is_active=True, company__is_verified=True, company__is_blocked=False, company__fraud_blocked=False).count(),
        'debtors': Company.objects.filter(invoices__status='pending').select_related('owner').annotate(
            unpaid_count=Count('invoices', filter=Q(invoices__status='pending')),
            unpaid_amount=Sum('invoices__amount', filter=Q(invoices__status='pending')),
            overdue_count=Count('invoices', filter=Q(invoices__status='pending', invoices__due_date__lt=timezone.localdate())),
        ).order_by('-unpaid_amount', 'pk'),
        'no_show_total': NoShowReport.objects.filter(dismissed_at__isnull=True).count(),
        'no_show_pending': NoShowReport.objects.filter(dismissed_at__isnull=True, checked_at__isnull=True).count(),
        'attended_bookings': Booking.objects.filter(status__in=['confirmed','completed']).count(),
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
    from business.models import Company
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
        # Поиск по email, имени, фамилии, телефону или названию компании
        users = users.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(company__name__icontains=query)
        )

    context = {
        'users': users,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'query': query,
        'title': 'Пользователи',
    }
    return render(request, 'dashboard/users/list.html', context)


@admin_required
def user_detail(request, pk):
    """Детальная информация о пользователе"""
    user = get_object_or_404(User, pk=pk)

    # Передаем API ключ в шаблон
    from decouple import config
    yandex_api_key = config('YANDEX_MAPS_API_KEY', default='')

    # Получаем компанию пользователя (если есть)
    company = None
    if user.role == 'entrepreneur':
        try:
            company = user.company
        except Company.DoesNotExist:
            pass

    context = {
        'fraud_blocks': company.fraud_blocks.select_related('confirmed_by', 'lifted_by') if company else [],
        'security_events': user.security_events.select_related('matched_block')[:30] if company else [],
        'user_obj': user,
        'company': company,
        'title': f'{user.email} ({company.name if company else "Без компании"})',
        'yandex_api_key': yandex_api_key,
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

        # Получаем название компании для отображения
        display_name = user.email
        if user.role == 'entrepreneur':
            try:
                display_name = user.company.name
            except Company.DoesNotExist:
                pass

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

    # Защита от блокировки самого себя
    if request.user.pk == user.pk:
        messages.error(request, 'Нельзя заблокировать самого себя')
        return redirect('dashboard:user_list')

    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()

        # Получаем название компании для отображения
        display_name = user.email
        if user.role == 'entrepreneur':
            try:
                display_name = user.company.name
            except Company.DoesNotExist:
                pass

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

            # Получаем название компании для отображения
            display_name = user.email
            if user.role == 'entrepreneur':
                try:
                    display_name = user.company.name
                except Company.DoesNotExist:
                    pass

            messages.success(request, f'Роль пользователя "{display_name}" изменена с "{old_role}" на "{user.get_role_display()}"')

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({'success': True, 'new_role': user.get_role_display()})

        return redirect('dashboard:user_list')

    return redirect('dashboard:user_list')


@admin_required
def user_toggle_services(request, pk):
    """Ручные санкции: скрыть услуги, сохранив доступ к ЛК и счетам."""
    from business.models import Company
    company = get_object_or_404(Company, owner_id=pk, owner__role='entrepreneur')
    if request.method == 'POST':
        if company.fraud_blocked:
            messages.error(request, 'Действует антифрод-ограничение. Сначала рассмотрите запись в реестре блокировок.')
            return redirect('dashboard:user_detail', pk=pk)
        company.is_blocked = not company.is_blocked
        company.save(update_fields=['is_blocked', 'updated_at'])
        messages.success(request, 'Все услуги предпринимателя скрыты.' if company.is_blocked else 'Услуги разблокированы.')
    return redirect('dashboard:user_detail', pk=pk)


@admin_required
def user_verify(request, pk):
    """Подтверждение компании предпринимателя (верификация)"""
    from business.models import Company
    user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        if user.role == 'entrepreneur':
            try:
                company = user.company
                from accounts.security import refresh_fraud_flags
                refresh_fraud_flags()
                company.refresh_from_db()
                if company.fraud_blocked:
                    messages.error(request, 'Компания ограничена антифрод-реестром.')
                    return redirect('dashboard:user_detail', pk=pk)
                company.is_verified = True
                company.save()
                messages.success(request, f'Компания "{company.name}" успешно проверена и верифицирована')
            except Company.DoesNotExist:
                messages.error(request, 'Компания не найдена')
        else:
            messages.error(request, 'Верифицировать можно только компанию предпринимателя')

        return redirect('dashboard:user_detail', pk=pk)

    return redirect('dashboard:user_detail', pk=pk)


@admin_required
def payment_report(request):
    import csv
    from django.http import HttpResponse
    from django.core.paginator import Paginator
    companies = Company.objects.select_related('owner').annotate(
        paid_count=Count('invoices', filter=Q(invoices__status='paid')),
        pending_count=Count('invoices', filter=Q(invoices__status='pending')),
        paid_amount=Sum('invoices__amount', filter=Q(invoices__status='paid')),
        pending_amount=Sum('invoices__amount', filter=Q(invoices__status='pending')),
    )
    city = request.GET.get('city', '').strip()
    status = request.GET.get('status', '')
    if city == '__empty__':
        companies = companies.filter(city='')
    elif city:
        companies = companies.filter(city__iexact=city)
    if status == 'paid':
        companies = companies.filter(paid_count__gt=0, pending_count=0)
    elif status == 'unpaid':
        companies = companies.filter(pending_count__gt=0)
    elif status == 'none':
        companies = companies.filter(paid_count=0, pending_count=0)
    companies = companies.order_by('city', 'name', 'pk')
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="payments-report.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Город', 'Компания', 'Email', 'Оплачено счетов', 'Не оплачено счетов', 'Оплачено, руб.', 'К оплате, руб.'])
        def safe(value):
            text = str(value)
            return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text
        for company in companies.iterator():
            writer.writerow([safe(company.city), safe(company.name), safe(company.owner.email), company.paid_count, company.pending_count, company.paid_amount or 0, company.pending_amount or 0])
        return response
    return render(request, 'dashboard/payment_report.html', {
        'companies': Paginator(companies, 30).get_page(request.GET.get('page')),
        'cities': Company.objects.exclude(city='').values_list('city', flat=True).distinct().order_by('city'),
        'city': city, 'status': status, 'title': 'Отчёт по оплатам',
    })


@admin_required
def no_show_reports(request):
    from django.core.exceptions import ValidationError
    from django.core.paginator import Paginator
    if request.method == 'POST':
        try:
            report_id = int(request.POST.get('report_id', ''))
        except (ValueError, TypeError):
            messages.error(request, 'Некорректный номер сообщения.')
            return redirect('dashboard:no_show_reports')
        report = get_object_or_404(NoShowReport, pk=report_id)
        if request.POST.get('action') == 'dismiss':
            from business.reliability import dismiss_no_show
            try:
                dismiss_no_show(report.pk, request.user, request.POST.get('reason',''))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
        elif request.POST.get('action') == 'check':
            NoShowReport.objects.filter(pk=report.pk, dismissed_at__isnull=True).update(checked_at=timezone.now())
        return redirect('dashboard:no_show_reports')
    reports = NoShowReport.objects.select_related('booking__service__company__owner','reported_by','dismissed_by')
    unreliable_clients = []
    seen = set()
    for report in reports.filter(dismissed_at__isnull=True):
        booking = report.booking
        identity = booking.normalized_phone or booking.normalized_email or str(booking.visitor_id)
        if identity not in seen and booking.no_show_count >= 3:
            seen.add(identity)
            unreliable_clients.append(booking)
    return render(request, 'dashboard/no_show_reports.html', {'title':'Неявки клиентов', 'reports':Paginator(reports,30).get_page(request.GET.get('page')), 'unreliable_clients':unreliable_clients})
