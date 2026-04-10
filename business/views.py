from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime, time
from django.http import JsonResponse
from .models import Company, Employee, Service, ServiceCategory, ServiceTimeSlot, Booking, Payment
from .forms import CompanyForm, EmployeeForm, ServiceForm, PaymentForm
from companies.models import Category, Subcategory


@login_required
def subcategories_api_view(request):
    """API для получения подкатегорий по категории"""
    category_id = request.GET.get('category')
    if category_id:
        subcategories = Subcategory.objects.filter(category_id=category_id).values('pk', 'name')
        return JsonResponse(list(subcategories), safe=False)
    return JsonResponse([], safe=False)


@login_required
def company_profile_view(request):
    """Просмотр профиля компании"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        return redirect('business:company_edit')
    
    employees = company.employees.all()
    services = company.services.all()
    bookings = Booking.objects.filter(service__company=company).order_by('-created_at')[:10]
    pending_bookings_count = Booking.objects.filter(service__company=company, status='pending').count()
    services_pending_count = company.services.filter(status='pending_payment').count()
    
    context = {
        'company': company,
        'employees': employees,
        'services': services,
        'bookings': bookings,
        'pending_bookings_count': pending_bookings_count,
        'services_pending_count': services_pending_count,
    }
    return render(request, 'business/company_profile.html', context)


@login_required
def company_edit_view(request):
    """Создание/редактирование профиля компании"""
    try:
        company = request.user.company
        is_create = False
    except Company.DoesNotExist:
        company = None
        is_create = True
    
    if request.method == 'POST':
        form = CompanyForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            company = form.save(commit=False)
            if is_create:
                company.owner = request.user
            company.save()
            messages.success(request, 'Профиль компании успешно сохранен!')
            return redirect('business:company_profile')
    else:
        form = CompanyForm(instance=company)
    
    return render(request, 'business/company_form.html', {'form': form, 'is_create': is_create})


@login_required
def employee_list_view(request):
    """Список сотрудников"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    employees = company.employees.all()
    return render(request, 'business/employee_list.html', {'employees': employees, 'company': company})


@login_required
def employee_create_view(request):
    """Создание сотрудника"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            # Сохраняем с commit=False чтобы сначала установить company
            employee = form.save(commit=False)
            # Устанавливаем компанию перед сохранением
            employee.company = company
            employee.save()
            messages.success(request, 'Сотрудник успешно добавлен! Теперь он может войти в ЛК используя email и пароль.')
            return redirect('business:employee_list')
    else:
        form = EmployeeForm()
    
    return render(request, 'business/employee_form.html', {'form': form, 'company': company, 'is_create': True})


@login_required
def employee_edit_view(request, pk):
    """Редактирование сотрудника"""
    try:
        company = request.user.company
        employee = company.employees.get(pk=pk)
    except (Company.DoesNotExist, Employee.DoesNotExist):
        messages.error(request, 'Сотрудник не найден')
        return redirect('business:employee_list')
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, 'Данные сотрудника обновлены!')
            return redirect('business:employee_list')
    else:
        form = EmployeeForm(instance=employee)
    
    return render(request, 'business/employee_form.html', {'form': form, 'company': company, 'employee': employee, 'is_create': False})


@login_required
def employee_delete_view(request, pk):
    """Удаление сотрудника"""
    try:
        company = request.user.company
        employee = company.employees.get(pk=pk)
    except (Company.DoesNotExist, Employee.DoesNotExist):
        messages.error(request, 'Сотрудник не найден')
        return redirect('business:employee_list')
    
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Сотрудник удален!')
        return redirect('business:employee_list')
    
    return render(request, 'business/employee_confirm_delete.html', {'employee': employee})


@login_required
def service_list_view(request):
    """Список услуг компании"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    services = company.services.all().select_related('category')
    return render(request, 'business/service_list.html', {'services': services, 'company': company})


@login_required
def service_create_view(request):
    """Создание услуги"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            service = form.save(commit=False)
            service.company = company
            service.status = 'pending_payment'
            service.save()
            # Сохраняем сотрудников
            employees = form.cleaned_data.get('employees')
            if employees:
                service.employees.set(employees)
            messages.success(request, 'Услуга создана! Теперь оплатите её для публикации.')
            return redirect('business:payment_create', service_id=service.pk)
    else:
        form = ServiceForm(company=company)
    
    return render(request, 'business/service_form.html', {
        'form': form, 
        'company': company,
        'is_create': True,
    })


@login_required
def service_edit_view(request, pk):
    """Редактирование услуги"""
    try:
        company = request.user.company
        service = company.services.get(pk=pk)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service, company=company)
        if form.is_valid():
            service = form.save(commit=False)
            if service.status == 'inactive':
                service.status = 'pending_payment'
            service.save()
            # Сохраняем сотрудников
            employees = form.cleaned_data.get('employees')
            if employees is not None:
                service.employees.set(employees)
            messages.success(request, 'Услуга обновлена!')
            return redirect('business:service_list')
    else:
        form = ServiceForm(instance=service, company=company)
    
    return render(request, 'business/service_form.html', {'form': form, 'company': company, 'service': service, 'is_create': False})


@login_required
def service_delete_view(request, pk):
    """Удаление услуги"""
    try:
        company = request.user.company
        service = company.services.get(pk=pk)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    if request.method == 'POST':
        service.delete()
        messages.success(request, 'Услуга удалена!')
        return redirect('business:service_list')
    
    return render(request, 'business/service_confirm_delete.html', {'service': service})


@login_required
def service_detail_view(request, pk):
    """Детальный просмотр услуги"""
    try:
        company = request.user.company
        service = company.services.get(pk=pk)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    time_slots = service.time_slots.filter(date__gte=timezone.now().date()).order_by('date', 'start_time')
    bookings = service.bookings.all().order_by('-created_at')
    
    return render(request, 'business/service_detail.html', {
        'service': service,
        'time_slots': time_slots,
        'bookings': bookings
    })


@login_required
def slot_manage_view(request, service_id):
    """Управление временными слотами в виде календарной сетки"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    # Получаем сотрудников услуги
    employees = service.employees.filter(is_active=True)
    
    # Дни недели (ПН-ВС)
    weekdays = [
        {'num': 0, 'name': 'Пн', 'full': 'Понедельник'},
        {'num': 1, 'name': 'Вт', 'full': 'Вторник'},
        {'num': 2, 'name': 'Ср', 'full': 'Среда'},
        {'num': 3, 'name': 'Чт', 'full': 'Четверг'},
        {'num': 4, 'name': 'Пт', 'full': 'Пятница'},
        {'num': 5, 'name': 'Сб', 'full': 'Суббота'},
        {'num': 6, 'name': 'Вс', 'full': 'Воскресенье'},
    ]
    
    # Часы (00:00 - 23:00)
    hours = list(range(24))
    
    return render(request, 'business/slot_manage.html', {
        'service': service,
        'employees': employees,
        'weekdays': weekdays,
        'hours': hours,
    })


@login_required
def slot_get_grid_view(request, service_id):
    """API для получения сетки слотов"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({'error': 'Услуга не найдена'}, status=404)
    
    employee_id = request.GET.get('employee')
    week_offset = int(request.GET.get('week_offset', 0))
    
    # Базовая дата - начало недели с учётом смещения
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    
    # Даты недели с учётом смещения
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
    
    # Получаем все слоты на эту неделю
    slots_qs = ServiceTimeSlot.objects.filter(
        service=service,
        date__in=week_dates
    )
    
    if employee_id:
        slots_qs = slots_qs.filter(employee_id=employee_id)
    
    # Строим сетку: ключ - "weekday_hour", значение - статус
    grid = {}
    for slot in slots_qs:
        weekday = slot.date.weekday()
        hour = slot.start_time.hour
        key = f"{weekday}_{hour}"
        grid[key] = {
            'is_booked': slot.is_booked,
            'slot_id': slot.pk,
            'has_booking': slot.booking is not None,
            'client_name': slot.booking.client_name if slot.booking else None,
        }
    
    return JsonResponse({
        'grid': grid,
        'week_dates': [d.isoformat() for d in week_dates],
    })


@login_required
def slot_update_grid_view(request, service_id):
    """API для обновления статуса слота в сетке"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не разрешён'}, status=405)
    
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({'error': 'Услуга не найдена'}, status=404)
    
    import json
    data = json.loads(request.body)
    weekday = data.get('weekday')
    hour = data.get('hour')
    action = data.get('action')  # 'toggle', 'set_free', 'set_busy'
    employee_id = data.get('employee')
    
    if weekday is None or hour is None:
        return JsonResponse({'error': 'Не указаны день или час'}, status=400)
    
    # Вычисляем дату
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    target_date = start_of_week + timedelta(days=int(weekday))
    
    start_time = time(int(hour), 0)
    end_time = time(int(hour) + 1, 0)
    
    # Фильтр по сотруднику
    slot_filter = {
        'service': service,
        'date': target_date,
        'start_time': start_time,
    }
    if employee_id:
        slot_filter['employee_id'] = employee_id
    
    slot = ServiceTimeSlot.objects.filter(**slot_filter).first()
    
    if slot is None:
        # Создаём новый слот
        slot = ServiceTimeSlot.objects.create(
            service=service,
            employee_id=employee_id if employee_id else None,
            date=target_date,
            start_time=start_time,
            end_time=end_time,
            is_booked=(action == 'set_busy'),
        )
    else:
        # Обновляем существующий
        if action == 'toggle':
            slot.is_booked = not slot.is_booked
        elif action == 'set_free':
            slot.is_booked = False
        elif action == 'set_busy':
            slot.is_booked = True
        
        if slot.is_booked:
            slot.booking = None
        slot.save()
    
    return JsonResponse({
        'success': True,
        'is_booked': slot.is_booked,
        'slot_id': slot.pk,
    })


@login_required
def slot_bulk_update_view(request, service_id):
    """Массовое обновление слотов (для popup настройки графика)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не разрешён'}, status=405)
    
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({'error': 'Услуга не найдена'}, status=404)
    
    import json
    data = json.loads(request.body)
    
    schedule_type = data.get('schedule_type')  # '5_2', 'all_week', 'specific_day'
    specific_day = data.get('specific_day')  # 0-6 для конкретного дня
    start_hour = int(data.get('start_hour', 9))
    end_hour = int(data.get('end_hour', 18))
    action = data.get('action')  # 'set_free', 'set_busy'
    employee_id = data.get('employee')
    set_others_busy = data.get('set_others_busy', False)  # Делать ли остальные слоты недоступными
    week_offset = int(data.get('week_offset', 0))
    
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    
    # Определяем дни для обработки
    days_to_process = []
    if schedule_type == '5_2':
        days_to_process = [0, 1, 2, 3, 4]  # Пн-Пт
    elif schedule_type == 'all_week':
        days_to_process = [0, 1, 2, 3, 4, 5, 6]  # Все дни
    elif schedule_type == 'specific_day' and specific_day is not None:
        days_to_process = [int(specific_day)]
    
    slots_created = 0
    slots_updated = 0
    
    for weekday in days_to_process:
        target_date = start_of_week + timedelta(days=weekday)
        
        for hour in range(0, 24):  # Проходим по всем часам суток
            start_time = time(hour, 0)
            end_time = time(hour + 1, 0)
            
            slot_filter = {
                'service': service,
                'date': target_date,
                'start_time': start_time,
            }
            if employee_id:
                slot_filter['employee_id'] = employee_id
            
            slot = ServiceTimeSlot.objects.filter(**slot_filter).first()
            
            # Определяем нужный статус
            if start_hour <= hour < end_hour:
                # В рабочем диапазоне
                should_be_booked = (action == 'set_busy')
            else:
                # Вне рабочего диапазона
                if set_others_busy and action == 'set_free':
                    # Если устанавливаем свободное время, то остальное делаем недоступным
                    should_be_booked = True
                else:
                    # Иначе оставляем как есть или создаём с текущим действием
                    should_be_booked = (action == 'set_busy')
            
            if slot is None:
                # Создаём новый слот только если он в диапазоне или set_others_busy=True
                if (start_hour <= hour < end_hour) or (set_others_busy and action == 'set_free'):
                    ServiceTimeSlot.objects.create(
                        service=service,
                        employee_id=employee_id if employee_id else None,
                        date=target_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_booked=should_be_booked,
                    )
                    slots_created += 1
            else:
                # Обновляем существующий слот
                if slot.is_booked != should_be_booked:
                    slot.is_booked = should_be_booked
                    if slot.is_booked:
                        slot.booking = None
                    slot.save()
                    slots_updated += 1
    
    return JsonResponse({
        'success': True,
        'slots_created': slots_created,
        'slots_updated': slots_updated,
    })


@login_required
def slot_generate_view(request, service_id):
    """Генерация временных слотов для каждого сотрудника"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    # Получаем сотрудников, привязанных к услуге
    employees = service.employees.filter(is_active=True)
    if not employees.exists():
        messages.error(request, 'К услуге не привязано ни одного сотрудника')
        return redirect('business:slot_manage', service_id=service_id)
    
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        start_hour = int(request.POST.get('start_hour', 9))
        end_hour = int(request.POST.get('end_hour', 18))
        interval = int(request.POST.get('interval', service.duration))
        
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            current_date = start_date_obj
            slots_created = 0
            
            while current_date <= end_date_obj:
                # Пропускаем выходные (суббота=5, воскресенье=6)
                if current_date.weekday() < 5:
                    current_time = time(start_hour, 0)
                    end_time = time(end_hour, 0)
                    
                    while current_time < end_time:
                        slot_end = datetime.combine(current_date, current_time) + timedelta(minutes=interval)
                        if slot_end.time() <= end_time:
                            # Создаем слот для каждого сотрудника
                            for employee in employees:
                                ServiceTimeSlot.objects.get_or_create(
                                    service=service,
                                    employee=employee,
                                    date=current_date,
                                    start_time=current_time,
                                    defaults={'end_time': slot_end.time()}
                                )
                                slots_created += 1
                        current_time = (datetime.combine(current_date, current_time) + timedelta(minutes=interval)).time()
                
                current_date += timedelta(days=1)
            
            messages.success(request, f'Создано {slots_created} временных слотов для {employees.count()} сотрудников с {start_date} по {end_date}')
            return redirect('business:slot_manage', service_id=service_id)
    
    context = {
        'service': service,
        'today': timezone.now(),
        'week_later': timezone.now() + timedelta(days=7),
        'employees_count': employees.count(),
    }
    return render(request, 'business/slot_generate.html', context)


@login_required
def slot_toggle_view(request, pk):
    """Переключение статуса слота (занят/свободен)"""
    try:
        company = request.user.company
        slot = ServiceTimeSlot.objects.get(pk=pk, service__company=company)
    except (Company.DoesNotExist, ServiceTimeSlot.DoesNotExist):
        messages.error(request, 'Слот не найден')
        return redirect('business:service_list')
    
    slot.is_booked = not slot.is_booked
    if slot.is_booked:
        slot.booking = None  # Сбрасываем бронирование при ручной блокировке
    slot.save()
    
    return redirect('business:slot_manage', service_id=slot.service.pk)


@login_required
def payment_create_view(request, service_id):
    """Создание платежа за услугу"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    if request.method == 'POST':
        payment = Payment.objects.create(
            service=service,
            amount=service.payment_amount,
            status='pending'
        )
        messages.success(request, 'Платеж создан. Переход к оплате...')
        return redirect('business:payment_process', pk=payment.pk)
    
    return render(request, 'business/payment_create.html', {'service': service})


@login_required
def payment_process_view(request, pk):
    """Обработка платежа (имитация)"""
    try:
        company = request.user.company
        payment = Payment.objects.get(pk=pk, service__company=company)
    except (Company.DoesNotExist, Payment.DoesNotExist):
        messages.error(request, 'Платеж не найден')
        return redirect('business:service_list')
    
    # Здесь должна быть интеграция с платежной системой
    # Для демонстрации просто помечаем как оплаченный
    
    if request.method == 'POST':
        payment.mark_as_paid()
        messages.success(request, 'Оплата прошла успешно! Услуга активирована.')
        return redirect('business:payment_success')
    
    return render(request, 'business/payment_process.html', {'payment': payment})


@login_required
def payment_success_view(request):
    """Страница успешной оплаты"""
    return render(request, 'business/payment_success.html')


@login_required
def booking_list_view(request):
    """Список бронирований"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    bookings = Booking.objects.filter(service__company=company).select_related('service', 'service__employee').order_by('-created_at')
    
    return render(request, 'business/booking_list.html', {'bookings': bookings, 'company': company})


@login_required
def booking_confirm_view(request, pk):
    """Подтверждение бронирования"""
    try:
        company = request.user.company
        booking = Booking.objects.get(pk=pk, service__company=company)
    except (Company.DoesNotExist, Booking.DoesNotExist):
        messages.error(request, 'Бронирование не найдено')
        return redirect('business:booking_list')
    
    booking.status = 'confirmed'
    booking.save()
    messages.success(request, 'Бронирование подтверждено!')
    
    return redirect('business:booking_list')


@login_required
def booking_cancel_view(request, pk):
    """Отмена бронирования"""
    try:
        company = request.user.company
        booking = Booking.objects.get(pk=pk, service__company=company)
    except (Company.DoesNotExist, Booking.DoesNotExist):
        messages.error(request, 'Бронирование не найдено')
        return redirect('business:booking_list')
    
    booking.status = 'cancelled'
    if booking.time_slots.exists():
        for slot in booking.time_slots.all():
            slot.is_booked = False
            slot.booking = None
            slot.save()
    booking.save()
    messages.success(request, 'Бронирование отменено!')
    
    return redirect('business:booking_list')
