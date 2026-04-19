from django.shortcuts import render
from django.db.models import Q
from django.conf import settings
from business.models import Service, Company
from companies.models import Category, Subcategory
import json


def search_view(request):
    """Страница поиска услуг"""
    query = request.GET.get('q', '')
    category_slug = request.GET.get('category', '')
    
    # Берём только активные услуги проверенных компаний
    services = Service.objects.select_related('company').filter(
        status='active',
        company__is_verified=True
    )
    categories = Category.objects.all()
    
    # Поиск по запросу
    if query:
        services = services.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Фильтр по категории
    if category_slug:
        subcategories = Subcategory.objects.filter(category__slug=category_slug)
        services = services.filter(subcategory__in=subcategories)
    
    # Получаем уникальные компании из найденных услуг для карты
    companies_with_coords = []
    seen_company_ids = set()
    
    for service in services:
        company = service.company
        if company.id not in seen_company_ids and company.latitude and company.longitude:
            seen_company_ids.add(company.id)
            companies_with_coords.append({
                'name': company.name,
                'address': company.address,
                'lat': float(company.latitude),
                'lng': float(company.longitude),
                'url': f"/company/{company.id}/" if hasattr(company, 'id') else "#",
                'logo': company.logo.url if company.logo else None,
            })
    
    context = {
        'query': query,
        'services': services,
        'categories': categories,
        'map_data': json.dumps(companies_with_coords),
        'has_map': len(companies_with_coords) > 0,
        'yandex_maps_api_key': settings.YANDEX_MAPS_API_KEY,
    }
    
    return render(request, 'search/search.html', context)
