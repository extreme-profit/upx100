from django.urls import path
from . import views

app_name = 'business'

urlpatterns = [
    # API для подкатегорий
    path('api/subcategories/', views.subcategories_api_view, name='subcategories_api'),
    
    # Публичный профиль компании (для клиентов)
    path('company/<int:company_id>/', views.company_public_profile_view, name='company_public_profile'),
    
    # Профиль компании (для предпринимателя и сотрудника)
    path('profile/', views.company_profile_view, name='company_profile'),
    path('profile/edit/', views.company_edit_view, name='company_edit'),
    
    # Сотрудники
    path('employees/', views.employee_list_view, name='employee_list'),
    path('employees/create/', views.employee_create_view, name='employee_create'),
    path('employees/<int:pk>/edit/', views.employee_edit_view, name='employee_edit'),
    path('employees/<int:pk>/delete/', views.employee_delete_view, name='employee_delete'),
    
    # Услуги
    path('services/', views.service_list_view, name='service_list'),
    path('services/create/', views.service_create_view, name='service_create'),
    path('services/<int:pk>/edit/', views.service_edit_view, name='service_edit'),
    path('services/<int:pk>/delete/', views.service_delete_view, name='service_delete'),
    path('services/<int:pk>/', views.service_detail_view, name='service_detail'),
    
    # Временные слоты
    path('services/<int:service_id>/slots/', views.slot_manage_view, name='slot_manage'),
    path('services/<int:service_id>/slots/generate/', views.slot_generate_view, name='slot_generate'),
    path('services/<int:service_id>/slots/api/grid/', views.slot_get_grid_view, name='slot_get_grid'),
    path('services/<int:service_id>/slots/api/update/', views.slot_update_grid_view, name='slot_update_grid'),
    path('services/<int:service_id>/slots/api/bulk/', views.slot_bulk_update_view, name='slot_bulk_update'),
    path('slots/<int:pk>/toggle/', views.slot_toggle_view, name='slot_toggle'),
    
    # Оплата
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('payments/<int:pk>/process/', views.payment_process_view, name='payment_process'),
    path('payments/success/', views.payment_success_view, name='payment_success'),
    
    # Бронирования (для просмотра предпринимателем)
    path('bookings/', views.booking_list_view, name='booking_list'),
    path('bookings/<int:pk>/confirm/', views.booking_confirm_view, name='booking_confirm'),
    path('bookings/<int:pk>/cancel/', views.booking_cancel_view, name='booking_cancel'),
    
    # Панель сотрудника
    path('employee/dashboard/', views.employee_dashboard_view, name='employee_dashboard'),
]
