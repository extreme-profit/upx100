from django.shortcuts import render
from django.db.models import Q
from services.models import Service
from companies.models import Category, Subcategory


def search_view(request):
    """Страница поиска услуг"""
    query = request.GET.get('q', '')
    category_slug = request.GET.get('category', '')
    
    services = Service.objects.filter(is_active=True)
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
