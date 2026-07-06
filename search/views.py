from django.shortcuts import render
from django.db.models import Q
from django.conf import settings
from business.models import Service
from companies.models import Category, Subcategory
import json
from .vector_search import search_similar
from django.utils import timezone


def search_view(request):
    """Страница поиска услуг"""
    query = request.GET.get('q', '')
    category_slug = request.GET.get('category', '')
    subcategory_slug = request.GET.get('subcategory', '')

    # Базовый queryset: только активные услуги проверенных компаний
    base_services = Service.objects.select_related('company').filter(
        payment_due_date__gt=timezone.now(),
        payment_due_date__isnull=False,
        company__is_verified=True
    )
    categories = Category.objects.all()

    # Поиск по запросу с использованием векторного поиска
    if query:
        # Сначала пытаемся найти семантически похожие услуги
        similar_service_ids = search_similar(query, top_k=20)

        if similar_service_ids:
            # Получаем услуги из уже отфильтрованного queryset'а по ID из векторного поиска
            vector_services = base_services.filter(id__in=similar_service_ids)

            # Традиционный поиск по ключевым словам
            keyword_services = base_services.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )

            # Объединяем результаты (векторный поиск в приоритете)
            all_service_ids = list(vector_services.values_list('id', flat=True))
            for service in keyword_services:
                if service.id not in all_service_ids:
                    all_service_ids.append(service.id)

            services = base_services.filter(id__in=all_service_ids)
        else:
            # Если векторный поиск не дал результатов, используем традиционный
            services = base_services.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )
    else:
        # Если нет поискового запроса, показываем все активные услуги
        services = base_services

    # Фильтр по категории
    selected_subcategories = []
    if category_slug:
        subcategories = Subcategory.objects.filter(category__slug=category_slug)
        selected_subcategories = list(subcategories)
        services = services.filter(subcategory__in=subcategories)

        # Если выбрана подкатегория, фильтруем ещё по ней
        if subcategory_slug:
            services = services.filter(subcategory__slug=subcategory_slug)

    # Получаем уникальные компании из найденных услуг для карты
    companies_with_coords = []
    seen_company_ids = set()

    for service in services:
        company = service.company
        if company.id not in seen_company_ids and company.latitude and company.longitude:
            seen_company_ids.add(company.id)
            companies_with_coords.append({
                'id': company.id,
                'name': company.name,
                'address': company.address,
                'lat': float(company.latitude),
                'lng': float(company.longitude),
                'url': f"/company/{company.id}/",
                'logo': company.logo.url if company.logo else None,
            })

    context = {
        'query': query,
        'services': services,
        'categories': categories,
        'selected_category': category_slug,
        'selected_subcategory': subcategory_slug,
        'selected_subcategories': selected_subcategories,
        'map_data': json.dumps(companies_with_coords),
        'has_map': len(companies_with_coords) > 0,
        'yandex_maps_api_key': settings.YANDEX_MAPS_API_KEY,
        'company_url_name': 'business:company_public_profile',
    }

    return render(request, 'search/search.html', context)
