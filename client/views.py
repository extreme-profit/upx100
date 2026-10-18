from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from business.models import Company, Service, ServiceTimeSlot, Booking, Employee
from companies.models import Category
from django.core.exceptions import ValidationError
from .forms import BookingForm
from business.booking_workflow import create_booking, cancel_client_booking
from business.timezones import slot_start
from business.models import Review
from business.reliability import client_ip
from django.core import signing
from django.http import Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie
from django.core.paginator import Paginator
from django.db.models import Max, Q, Avg, Count, F


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
    employees = service.employees.filter(is_active=True).prefetch_related('user').annotate(rating_avg=Avg('reviews__rating', filter=Q(reviews__booking__status__in=['confirmed', 'completed'])), rating_count=Count('reviews', filter=Q(reviews__booking__status__in=['confirmed', 'completed']))).order_by(F('rating_avg').desc(nulls_last=True), '-rating_count', 'pk')
    
    # Получаем выбранного сотрудника (если есть)
    employee_id = request.GET.get('employee_id')
    selected_employee = None
    if employee_id:
        try:
            selected_employee = employees.get(pk=employee_id)
        except Employee.DoesNotExist:
            pass
    
    # Недели отсчитываются от сегодняшнего дня, по семь дней на страницу.
    today = timezone.localdate(timezone=service.company.tzinfo)
    now = timezone.now()
    
    time_slots_qs = ServiceTimeSlot.objects.filter(
        service=service,
        date__gte=today,
        is_booked=False
    ).filter(
        Q(employee__isnull=True) | Q(employee__is_active=True)
    ).select_related('employee__user').order_by('date', 'start_time')
    
    # Фильтруем по сотруднику если выбран
    if selected_employee:
        time_slots_qs = time_slots_qs.filter(employee=selected_employee)

    last_date = time_slots_qs.aggregate(last_date=Max('date'))['last_date'] or today
    week_count = (last_date - today).days // 7 + 1
    week_page = Paginator(range(week_count), 1).get_page(request.GET.get('week', 1))
    week_start = today + timedelta(days=(week_page.number - 1) * 7)
    week_end = week_start + timedelta(days=6)
    time_slots_qs = time_slots_qs.filter(date__range=(week_start, week_end))
    
    # Фильтруем прошедшие слоты
    filtered_slots = []
    for slot in time_slots_qs:
        try:
            slot_datetime = slot_start(slot)
        except ValidationError:
            continue
        if slot_datetime > now:
            filtered_slots.append(slot)
    
    # Группируем слоты по датам
    slots_by_date = {}
    for slot in filtered_slots:
        date_str = slot.date
        if date_str not in slots_by_date:
            slots_by_date[date_str] = []
        slots_by_date[date_str].append(slot)
    
    # Даты для отображения "Сегодня" и "Завтра"
    today_str = today
    tomorrow_str = today + timedelta(days=1)
    
    context = {
        'service': service,
        'employees': employees,
        'selected_employee': selected_employee,
        'slots_by_date': slots_by_date,
        'today_str': today_str,
        'tomorrow_str': tomorrow_str,
        'master_reviews': Review.objects.filter(employee__in=employees, booking__status__in=['confirmed', 'completed']).select_related('employee__user')[:20],
        'week_page': week_page,
        'week_start': week_start,
        'week_end': week_end,
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
                booking = create_booking(service.pk, form.cleaned_data, visitor_id=request.booking_visitor, client_ip=client_ip(request))
            except (ServiceTimeSlot.DoesNotExist, Service.DoesNotExist, ValidationError):
                messages.error(request, 'Выбранное время недоступно. Выберите другое.')
                return redirect('client:service_detail', service_id=service.pk)
            request.session['last_booking_id'] = booking.pk
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
    
    from business.reliability import monthly_no_shows, WARNING
    context = {
        'reliability_warning': WARNING if monthly_no_shows(request.booking_visitor, request.POST.get('client_email',''), request.POST.get('client_phone','')) >= 3 else '',
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
    from business.reliability import WARNING
    context = {'booking': booking, 'reliability_warning': WARNING if booking.no_show_count >= 3 else ''}
    return render(request, 'client/booking_success.html', context)


@require_http_methods(['GET', 'POST'])
def booking_cancel_view(request, token):
    try:
        data = signing.loads(token, salt='client.booking.cancel')
        booking = get_object_or_404(Booking.objects.select_related('service__company'), pk=data['booking_id'])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise Http404
    if request.method == 'POST':
        cancel_client_booking(booking.pk)
        return redirect('client:booking_cancel', token=token)
    return render(request, 'client/booking_cancel.html', {'booking': booking})


@never_cache
@vary_on_cookie
def booking_history_view(request):
    from django.db.models import Q
    from business.notifications import cancellation_url
    from business.reviews import can_review, review_url
    bookings = Booking.objects.filter(visitor_id=request.booking_visitor).select_related('service__company', 'review').order_by('-created_at')
    active = Q(status__in=['pending', 'confirmed']) & (Q(appointment_at__gte=timezone.now()) | Q(appointment_at__isnull=True))
    tab = request.GET.get('tab', 'current')
    bookings = bookings.exclude(active) if tab == 'past' else bookings.filter(active)
    page = Paginator(bookings, 15).get_page(request.GET.get('page'))
    for booking in page:
        booking.review_link = review_url(booking) if can_review(booking) and not hasattr(booking, 'review') else ''
        booking.cancel_url = cancellation_url(booking) if booking.status in ('pending', 'confirmed') else ''
    return render(request, 'client/booking_history.html', {'bookings': page, 'tab': tab})


@never_cache
@require_http_methods(['GET', 'POST'])
def booking_review_view(request, token):
    from business.reviews import can_review, save_review
    from .forms import ReviewForm
    booking = get_object_or_404(Booking.objects.select_related('employee__user', 'service', 'review'), review_token=token)
    existing = getattr(booking, 'review', None)
    if not existing and not can_review(booking):
        return render(request, 'client/booking_review.html', {'booking':booking, 'unavailable':True}, status=403)
    form = ReviewForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and not existing and form.is_valid():
        review = save_review(booking.pk, form.cleaned_data['rating'], form.cleaned_data['comment'])
        if review is None:
            return render(request, 'client/booking_review.html', {'booking':booking, 'unavailable':True}, status=403)
        return redirect('client:booking_review', token=token)
    return render(request, 'client/booking_review.html', {'booking':booking, 'review':existing, 'form':form})
