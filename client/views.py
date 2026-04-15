from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from business.models import Company, Service, ServiceTimeSlot, Booking
from companies.models import Category


def companies_list_view(request):
    """Список всех компаний для клиентов"""
    category_slug = request.GET.get('category')
    
    companies = Company.objects.all()
    categories = Category.objects.all()
    
    if category_slug:
        companies = companies.filter(services__category__slug=category_slug).distinct()
    
    context = {
        'companies': companies,
        'categories': categories,
        'selected_category': category_slug,
    }
    return render(request, 'client/companies_list.html', context)


def company_detail_view(request, company_id):
    """Страница компании с услугами для клиентов"""
    company = get_object_or_404(Company, pk=company_id)
    services = company.services.filter(status='active').prefetch_related('employees')
    
    context = {
        'company': company,
        'services': services,
    }
    return render(request, 'client/company_detail.html', context)


def service_detail_view(request, service_id):
    """Страница услуги с возможностью записи"""
    service = get_object_or_404(Service, pk=service_id, status='active')
    
    # Получаем доступные слоты на ближайшие 14 дней
    today = timezone.now().date()
    end_date = today + timedelta(days=14)
    
    time_slots = ServiceTimeSlot.objects.filter(
        service=service,
        date__range=(today, end_date),
        is_booked=False
    ).select_related('employee').order_by('date', 'start_time')
    
    # Группируем слоты по датам
    slots_by_date = {}
    for slot in time_slots:
        date_str = slot.date.strftime('%Y-%m-%d')
        if date_str not in slots_by_date:
            slots_by_date[date_str] = []
        slots_by_date[date_str].append(slot)
    
    # Даты для отображения "Сегодня" и "Завтра"
    today_str = today.strftime('%Y-%m-%d')
    tomorrow_str = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    context = {
        'service': service,
        'slots_by_date': slots_by_date,
        'today_str': today_str,
        'tomorrow_str': tomorrow_str,
    }
    return render(request, 'client/service_detail.html', context)


def booking_create_view(request, service_id):
    """Создание бронирования"""
    service = get_object_or_404(Service, pk=service_id, status='active')
    
    if request.method == 'POST':
        slot_id = request.POST.get('slot_id')
        client_name = request.POST.get('client_name')
        client_phone = request.POST.get('client_phone')
        client_email = request.POST.get('client_email')
        notes = request.POST.get('notes', '')
        
        if not slot_id or not client_name or not client_phone:
            messages.error(request, 'Заполните обязательные поля')
            return redirect('client:service_detail', service_id=service.pk)
        
        try:
            slot = ServiceTimeSlot.objects.get(pk=slot_id, service=service, is_booked=False)
        except ServiceTimeSlot.DoesNotExist:
            messages.error(request, 'Выбранное время уже занято')
            return redirect('client:service_detail', service_id=service.pk)
        
        # Создаем бронирование
        booking = Booking.objects.create(
            service=service,
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            notes=notes,
            status='pending'
        )
        
        # Помечаем слот как забронированный
        slot.is_booked = True
        slot.booking = booking
        slot.save()
        
        messages.success(request, 'Ваша заявка на запись успешно создана! Мы свяжемся с вами для подтверждения.')
        return redirect('client:booking_success', booking_id=booking.pk)
    
    # GET запрос - показываем форму
    slot_id = request.GET.get('slot_id')
    slot = None
    if slot_id:
        slot = get_object_or_404(ServiceTimeSlot, pk=slot_id, service=service, is_booked=False)
    
    context = {
        'service': service,
        'slot': slot,
    }
    return render(request, 'client/booking_form.html', context)


def booking_success_view(request, booking_id):
    """Страница успешного бронирования"""
    booking = get_object_or_404(Booking, pk=booking_id)
    context = {'booking': booking}
    return render(request, 'client/booking_success.html', context)
