from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime, time
from .models import Company, Employee, Service, ServiceCategory, ServiceTimeSlot, Booking, Payment
from .forms import CompanyForm, EmployeeForm, ServiceForm, PaymentForm


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
    services_pending_count = company.services.filter(status='pending_payment').count()
    
    context = {
        'company': company,
        'employees': employees,
        'services': services,
        'bookings': bookings,
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
            employee = form.save(commit=False)
            employee.company = company
            employee.save()
            messages.success(request, 'Сотрудник успешно добавлен!')
            return redirect('business:employee_list')
    else:
        form = EmployeeForm()
    
    return render(request, 'business/employee_form.html', {'form': form, 'company': company})


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
    
    return render(request, 'business/employee_form.html', {'form': form, 'company': company, 'employee': employee})


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
    
    services = company.services.all().select_related('category', 'employee')
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
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.company = company
            service.payment_amount = service.price  # Пример: оплата равна цене услуги
            service.status = 'pending_payment'
            service.save()
            messages.success(request, 'Услуга создана! Теперь оплатите её для публикации.')
            return redirect('business:payment_create', service_id=service.pk)
    else:
        form = ServiceForm()
        form.fields['employee'].queryset = company.employees.filter(is_active=True)
    
    categories = ServiceCategory.objects.all()
    return render(request, 'business/service_form.html', {
        'form': form, 
        'company': company,
        'categories': categories
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
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            service = form.save(commit=False)
            if service.status == 'inactive':
                service.status = 'pending_payment'
            service.save()
            messages.success(request, 'Услуга обновлена!')
            return redirect('business:service_list')
    else:
        form = ServiceForm(instance=service)
        form.fields['employee'].queryset = company.employees.filter(is_active=True)
    
    return render(request, 'business/service_form.html', {'form': form, 'company': company, 'service': service})


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
    """Управление временными слотами"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    date_filter = request.GET.get('date', timezone.now().date())
    time_slots = service.time_slots.filter(date=date_filter).order_by('start_time')
    
    return render(request, 'business/slot_manage.html', {
        'service': service,
        'time_slots': time_slots,
        'current_date': date_filter
    })


@login_required
def slot_generate_view(request, service_id):
    """Генерация временных слотов"""
    try:
        company = request.user.company
        service = company.services.get(pk=service_id)
    except (Company.DoesNotExist, Service.DoesNotExist):
        messages.error(request, 'Услуга не найдена')
        return redirect('business:service_list')
    
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        start_hour = int(request.POST.get('start_hour', 9))
        end_hour = int(request.POST.get('end_hour', 18))
        interval = int(request.POST.get('interval', service.duration))
        
        if start_date and end_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            current_date = start_date
            while current_date <= end_date:
                # Пропускаем выходные (суббота=5, воскресенье=6)
                if current_date.weekday() < 5:
                    current_time = time(start_hour, 0)
                    end_time = time(end_hour, 0)
                    
                    while current_time < end_time:
                        slot_end = datetime.combine(current_date, current_time) + timedelta(minutes=interval)
                        if slot_end.time() <= end_time:
                            ServiceTimeSlot.objects.get_or_create(
                                service=service,
                                date=current_date,
                                start_time=current_time,
                                defaults={'end_time': slot_end.time()}
                            )
                        current_time = (datetime.combine(current_date, current_time) + timedelta(minutes=interval)).time()
                
                current_date += timedelta(days=1)
            
            messages.success(request, f'Временные слоты созданы с {start_date} по {end_date}')
            return redirect('business:slot_manage', service_id=service_id)
    
    return render(request, 'business/slot_generate.html', {'service': service})


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
