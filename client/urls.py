from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    path('companies/', views.companies_list_view, name='companies_list'),
    path('company/<int:company_id>/', views.company_detail_view, name='company_detail'),
    path('service/<int:service_id>/', views.service_detail_view, name='service_detail'),
    path('service/<int:service_id>/book/', views.booking_create_view, name='booking_create'),
    path('booking/success/<int:booking_id>/', views.booking_success_view, name='booking_success'),
]
