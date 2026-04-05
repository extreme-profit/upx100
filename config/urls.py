"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include
from dashboard.views import home_view

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),
    path('search/', include('search.urls', namespace='search')),
]
