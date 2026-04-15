from django.shortcuts import render
from django.db.models import Q
from business.models import Service
from companies.models import Category, Subcategory


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
    
    context = {
        'query': query,
        'services': services,
        'categories': categories,
    }
    
    return render(request, 'search/search.html', context)
