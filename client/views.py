from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from business.models import Company, Service, ServiceTimeSlot, Booking, Employee
from companies.models import Category
from django.core.exceptions import ValidationError
from .forms import BookingForm
from business.booking_workflow import create_booking


def companies_list_view(request):
    """Список всех компаний для клиентов"""
    category_slug = request.GET.get('category')
    subcategory_slug = request.GET.get('subcategory')

    # Показываем только проверенные компании
    companies = Company.objects.filter(is_verified=True, is_blocked=False, owner__is_active=True)
    categories = Category.objects.all()

    if category_slug:
        # Публикация бесплатна; архивные услуги не участвуют в фильтрах.
        companies = companies.filter(
            services__category__slug=category_slug,
            services__is_archived=False,
        ).distinct()

        # Если выбрана подкатегория, фильтруем ещё по ней
        if subcategory_slug:
            companies = companies.filter(
                services__subcategory__slug=subcategory_slug
            ).distinct()

    # Для отображения количества активных услуг у каждой компании
    for company in companies:
        company.active_services_count = Service.objects.visible().filter(
            company=company,
        ).count()

    context = {
        'companies': companies,
        'categories': categories,
        'selected_category': category_slug,
        'selected_subcategory': subcategory_slug,
    }
    return render(request, 'client/companies_list.html', context)


def company_detail_view(request, company_id):
    """Страница компании с услугами для клиентов"""
    # Проверяем что компания проверена
    company = get_object_or_404(Company, pk=company_id, is_verified=True, is_blocked=False, owner__is_active=True)
    # Показываем только активные услуги
    services = company.services.visible().filter(
        company__is_verified=True  # Компания проверена
    ).prefetch_related('employees', 'category', 'subcategory')
    
    context = {
        'company': company,
        'services': services,
    }
    return render(request, 'client/company_detail.html', context)


def service_detail_view(request, service_id):
    """Страница услуги с возможностью записи"""
    service = get_object_or_404(
        Service.objects.visible().select_related('company'),
        pk=service_id,
        company__is_verified=True  # Компания проверена
    )
    
    # Получаем всех сотрудников услуги
    employees = service.employees.filter(is_active=True).prefetch_related('user')
    
    # Получаем выбранного сотрудника (если есть)
    employee_id = request.GET.get('employee_id')
    selected_employee = None
    if employee_id:
        try:
            selected_employee = employees.get(pk=employee_id)
        except Employee.DoesNotExist:
            pass
    
    # Получаем доступные слоты на ближайшие 14 дней
    today = timezone.localdate()
    end_date = today + timedelta(days=14)
    now = timezone.now()
    
    time_slots_qs = ServiceTimeSlot.objects.filter(
        service=service,
        date__range=(today, end_date),
        is_booked=False
    ).select_related('employee').order_by('date', 'start_time')
    
    # Фильтруем по сотруднику если выбран
    if selected_employee:
        time_slots_qs = time_slots_qs.filter(employee=selected_employee)
    
    # Фильтруем прошедшие слоты
    filtered_slots = []
    for slot in time_slots_qs:
        slot_datetime = timezone.make_aware(timezone.datetime.combine(slot.date, slot.start_time))
        if slot_datetime > now:
            filtered_slots.append(slot)
    
    # Группируем слоты по датам
    slots_by_date = {}
    for slot in filtered_slots:
        date_str = slot.date.strftime('%Y-%m-%d')
        if date_str not in slots_by_date:
            slots_by_date[date_str] = []
        slots_by_date[date_str].append(slot)
    
    # Даты для отображения "Сегодня" и "Завтра"
    today_str = today.strftime('%Y-%m-%d')
    tomorrow_str = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    context = {
        'service': service,
        'employees': employees,
        'selected_employee': selected_employee,
        'slots_by_date': slots_by_date,
        'today_str': today_str,
        'tomorrow_str': tomorrow_str,
    }
    return render(request, 'client/service_detail.html', context)


def booking_create_view(request, service_id):
    """Создание бронирования"""
    # Проверяем публикацию и отсутствие блокировки предпринимателя.
    service = get_object_or_404(
        Service.objects.visible().select_related('company'),
        pk=service_id,
        company__is_verified=True  # Компания проверена
    )
    
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            try:
                booking = create_booking(service.pk, form.cleaned_data)
            except (ServiceTimeSlot.DoesNotExist, Service.DoesNotExist, ValidationError):
                messages.error(request, 'Выбранное время недоступно. Выберите другое.')
                return redirect('client:service_detail', service_id=service.pk)
            request.session['last_booking_id'] = booking.pk
            messages.success(request, 'Заявка отправлена! Решение предпринимателя придёт на вашу почту.')
            return redirect('client:booking_success', booking_id=booking.pk)
    else:
        form = BookingForm()
    
    # GET запрос - показываем форму
    slot_id = request.POST.get('slot_id') if request.method == 'POST' else request.GET.get('slot_id')
    slot = None
    if slot_id:
        try:
            slot = get_object_or_404(ServiceTimeSlot, pk=slot_id, service=service, is_booked=False)
        except (ValueError, TypeError):
            slot = None
    
    context = {
        'service': service,
        'slot': slot,
        'employee': slot.employee if slot and slot.employee else None,
        'form': form,
    }
    return render(request, 'client/booking_form.html', context)


def booking_success_view(request, booking_id):
    """Страница успешного бронирования"""
    from django.http import Http404
    if request.session.get('last_booking_id') != booking_id:
        raise Http404
    booking = get_object_or_404(Booking, pk=booking_id)
    context = {'booking': booking}
    return render(request, 'client/booking_success.html', context)
