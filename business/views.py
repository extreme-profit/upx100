from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime, time
from django.http import JsonResponse
from .models import Company, Employee, Service, ServiceCategory, ServiceTimeSlot, Booking, Payment
from .forms import CompanyForm, EmployeeForm, ServiceForm, ServiceTimeSlotGenerateForm
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
            return redirect('business:service_detail', pk=service.pk)
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
    
    # Получаем интервал и время работы из сессии или используем значения по умолчанию
    interval = request.session.get(f'slot_duration_{service.id}', service.duration)
    if not interval:
        interval = 30  # Значение по умолчанию если ничего не найдено
    
    work_start_str = request.session.get(f'slot_work_start_{service.id}', '09:00')
    work_end_str = request.session.get(f'slot_work_end_{service.id}', '18:00')
    
    hours = []
    # Генерируем все возможные слоты с шагом interval минут от начала рабочего дня до конца
    start_parts = work_start_str.split(':')
    start_total = int(start_parts[0]) * 60 + int(start_parts[1])
    
    end_parts = work_end_str.split(':')
    end_total = int(end_parts[0]) * 60 + int(end_parts[1])
    
    for total_minutes in range(start_total, end_total + 1, interval):
        h = total_minutes // 60
        m = total_minutes % 60
        time_str = f"{h:02d}:{m:02d}"
        hours.append({'value': time_str, 'label': time_str})
    
    return render(request, 'business/slot_manage.html', {
        'service': service,
        'employees': employees,
        'weekdays': weekdays,
        'hours': hours,
        'interval': interval,
        'work_start': work_start_str,
        'work_end': work_end_str,
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
    
    # Получаем интервал из сессии (по умолчанию duration услуги)
    interval = request.session.get(f'slot_duration_{service_id}', service.duration)
    if not interval:
        interval = 30  # Значение по умолчанию
    
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
        minute = slot.start_time.minute
        # Создаем ключ с учётом интервала (например, 9_0, 9_15, 9_30, 9_45 для 15-минутного интервала)
        key = f"{weekday}_{hour}_{minute}"
        grid[key] = {
            'is_booked': slot.is_booked,
            'slot_id': slot.pk,
            'has_booking': slot.booking is not None,
            'client_name': slot.booking.client_name if slot.booking else None,
            'start_time': slot.start_time.strftime('%H:%M'),
            'end_time': slot.end_time.strftime('%H:%M'),
        }
    
    return JsonResponse({
        'grid': grid,
        'week_dates': [d.isoformat() for d in week_dates],
        'interval': interval,
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
    minute = data.get('minute', 0)  # Получаем минуты (по умолчанию 0)
    action = data.get('action')  # 'toggle', 'set_free', 'set_busy'
    employee_id = data.get('employee')
    
    # Получаем интервал из сессии
    interval = request.session.get(f'slot_duration_{service_id}', service.duration)
    if not interval:
        interval = 30  # Значение по умолчанию
    
    if weekday is None or hour is None:
        return JsonResponse({'error': 'Не указаны день или час'}, status=400)
    
    # Вычисляем дату
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    target_date = start_of_week + timedelta(days=int(weekday))
    
    start_time = time(int(hour), int(minute))
    # Вычисляем время окончания на основе интервала
    end_datetime = datetime.combine(target_date, start_time) + timedelta(minutes=interval)
    end_time = end_datetime.time()
    
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
    
    # Получаем интервал и длительность из сессии
    interval = request.session.get(f'slot_duration_{service_id}', service.duration)
    if not interval:
        interval = 30  # Значение по умолчанию
    
    duration = request.session.get(f'slot_duration_{service_id}', service.duration)
    if not duration:
        duration = 30  # Значение по умолчанию
    
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
        
        # Генерируем слоты на основе интервала - последовательно от start_hour до end_hour
        # Начинаем с start_hour:00 и двигаемся с шагом interval минут
        current_time = datetime.combine(target_date, time(start_hour, 0))
        end_time_limit = datetime.combine(target_date, time(end_hour, 0))
        
        while current_time < end_time_limit:
            start_time = current_time.time()
            
            # Вычисляем время окончания слота на основе длительности услуги
            end_datetime = current_time + timedelta(minutes=duration)
            end_time = end_datetime.time()
            
            # Если время окончания выходит за рамки end_hour, прекращаем
            if end_datetime > end_time_limit:
                break
            
            slot_filter = {
                'service': service,
                'date': target_date,
                'start_time': start_time,
            }
            if employee_id:
                slot_filter['employee_id'] = employee_id
            
            slot = ServiceTimeSlot.objects.filter(**slot_filter).first()
            
            # Определяем нужный статус
            should_be_booked = (action == 'set_busy')
            
            if slot is None:
                # Создаём новый слот
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
            
            # Переходим к следующему слоту с шагом interval
            current_time = current_time + timedelta(minutes=interval)
        
        # Если нужно сделать остальные слоты недоступными (вне рабочего времени)
        if set_others_busy and action == 'set_free':
            # Проходим по всем возможным слотам вне рабочего диапазона
            day_start = datetime.combine(target_date, time(0, 0))
            day_end = datetime.combine(target_date, time(23, 59))
            
            current_time = day_start
            while current_time <= day_end:
                start_time = current_time.time()
                end_datetime = current_time + timedelta(minutes=duration)
                
                # Проверяем, попадает ли слот в рабочее время
                work_start = datetime.combine(target_date, time(start_hour, 0))
                work_end = datetime.combine(target_date, time(end_hour, 0))
                
                # Если слот полностью вне рабочего времени
                if end_datetime <= work_start or current_time >= work_end:
                    slot_filter = {
                        'service': service,
                        'date': target_date,
                        'start_time': start_time,
                    }
                    if employee_id:
                        slot_filter['employee_id'] = employee_id
                    
                    slot = ServiceTimeSlot.objects.filter(**slot_filter).first()
                    
                    if slot is None:
                        ServiceTimeSlot.objects.create(
                            service=service,
                            employee_id=employee_id if employee_id else None,
                            date=target_date,
                            start_time=start_time,
                            end_time=end_datetime.time(),
                            is_booked=True,  # Делаем недоступным
                        )
                        slots_created += 1
                    elif not slot.is_booked:
                        slot.is_booked = True
                        slot.booking = None
                        slot.save()
                        slots_updated += 1
                
                current_time = current_time + timedelta(minutes=interval)
    
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
        # Получаем значения из сессии для initial
        initial_data = {}
        session_duration = request.session.get(f'slot_duration_{service_id}')
        if session_duration:
            initial_data['duration'] = session_duration
        
        form = ServiceTimeSlotGenerateForm(request.POST, service=service, initial=initial_data)
        if form.is_valid():
            schedule_type = form.cleaned_data['schedule_type']
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            start_time = form.cleaned_data['start_time']
            end_time = form.cleaned_data['end_time']
            duration = form.cleaned_data['duration']
            weekdays = form.cleaned_data.get('weekdays', [])
            
            # Сохраняем длительность и время работы в сессии для использования в slot_manage
            request.session[f'slot_duration_{service_id}'] = duration
            request.session[f'slot_work_start_{service_id}'] = start_time.strftime('%H:%M')
            request.session[f'slot_work_end_{service_id}'] = end_time.strftime('%H:%M')
            
            # Определяем дни для обработки
            days_to_process = []
            if schedule_type == '5_2':
                days_to_process = [0, 1, 2, 3, 4]  # Пн-Пт
            elif schedule_type == 'all_week':
                days_to_process = [0, 1, 2, 3, 4, 5, 6]  # Все дни
            elif schedule_type == 'specific':
                days_to_process = [int(d) for d in weekdays]
            
            # Генерируем слоты в указанном диапазоне дат
            slots_created = 0
            current_date = start_date
            
            while current_date <= end_date:
                # Проверяем, попадает ли день в выбранные дни недели
                weekday = current_date.weekday()
                if weekday in days_to_process:
                    # Генерируем слоты на основе длительности услуги
                    start_minutes = start_time.hour * 60 + start_time.minute
                    end_minutes = end_time.hour * 60 + end_time.minute
                    
                    current_minutes = start_minutes
                    while current_minutes + duration <= end_minutes:
                        start_hour = current_minutes // 60
                        start_minute = current_minutes % 60
                        slot_start_time = time(start_hour, start_minute)
                        
                        # Вычисляем время окончания слота
                        slot_end_minutes = current_minutes + duration
                        end_hour = slot_end_minutes // 60
                        end_min = slot_end_minutes % 60
                        slot_end_time = time(end_hour, end_min)
                        
                        # Создаем слот для каждого сотрудника
                        for employee in employees:
                            ServiceTimeSlot.objects.get_or_create(
                                service=service,
                                employee=employee,
                                date=current_date,
                                start_time=slot_start_time,
                                defaults={'end_time': slot_end_time}
                            )
                            slots_created += 1
                        
                        # Переходим к следующему слоту с шагом duration (интервал = длительности)
                        current_minutes += duration
                    
                    # Если нужно сделать остальные слоты недоступными (вне рабочего времени)
                    # Пропускаем этот шаг для простоты - можно добавить при необходимости
                
                current_date += timedelta(days=1)
            
            messages.success(request, f'Создано {slots_created} временных слотов для {employees.count()} сотрудников')
            return redirect('business:slot_manage', service_id=service_id)
    else:
        # Получаем значения из сессии для initial
        initial_data = {}
        session_duration = request.session.get(f'slot_duration_{service_id}')
        if session_duration:
            initial_data['duration'] = session_duration
        
        form = ServiceTimeSlotGenerateForm(service=service, initial=initial_data)
    
    context = {
        'service': service,
        'form': form,
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
def payment_process_view(request, pk):
    """Обработка платежа (имитация)"""
    try:
        company = request.user.company
        service = company.services.get(pk=pk)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    # Получаем или создаем платеж для услуги
    # Сначала проверяем, есть ли уже успешный платеж
    success_payment = Payment.objects.filter(service=service, status='success').first()
    if success_payment:
        messages.info(request, 'Услуга уже оплачена')
        return redirect('business:service_detail', pk=service.pk)

    # Пытаемся получить существующий неоплаченный платеж
    payment = Payment.objects.filter(service=service).exclude(status='success').first()
    if not payment:
        # Создаем новый платеж
        payment = Payment.objects.create(
            service=service,
            amount=service.price,
            status='pending'
        )

    # Если уже оплачено (проверка на всякий случай), перенаправляем на детальную страницу
    if payment.status == 'success':
        messages.info(request, 'Услуга уже оплачена')
        return redirect('business:service_detail', pk=service.pk)
    
    # Здесь должна быть интеграция с платежной системой
    # Для демонстрации просто помечаем как оплаченный
    
    if request.method == 'POST':
        payment.mark_as_paid()
        messages.success(request, 'Оплата прошла успешно! Услуга активирована.')
        return redirect('business:service_detail', pk=payment.service.pk)
    
    return render(request, 'business/payment_process.html', {'payment': payment})


@login_required
def payment_success_view(request):
    """Страница успешной оплаты"""
    return redirect('business:service_list')


@login_required
def booking_list_view(request):
    """Список бронирований"""
    try:
        company = request.user.company
    except Company.DoesNotExist:
        messages.error(request, 'Сначала создайте профиль компании')
        return redirect('business:company_edit')
    
    bookings = Booking.objects.filter(service__company=company).select_related('service', 'service__category', 'service__subcategory').order_by('-created_at')
    
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
