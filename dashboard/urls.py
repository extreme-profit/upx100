from django.urls import path
from . import views, fraud_views

app_name = 'dashboard'

urlpatterns = [
    path('blocks/', fraud_views.blocked_users, name='blocked_users'),
    path('users/<int:pk>/fraud/', fraud_views.confirm_user_fraud, name='confirm_user_fraud'),
    path('blocks/<int:pk>/lift/', fraud_views.lift_user_fraud, name='lift_user_fraud'),
    path('blocks/<int:pk>/export/', fraud_views.export_fraud, name='export_fraud'),
    path('no-shows/', views.no_show_reports, name='no_show_reports'),
    path('payments/', views.payment_report, name='payment_report'),
    # Главная
    path('', views.dashboard_home, name='home'),
    
    # Категории
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Подкатегории
    path('subcategories/', views.subcategory_list, name='subcategory_list'),
    path('subcategories/create/', views.subcategory_create, name='subcategory_create'),
    path('subcategories/<int:pk>/edit/', views.subcategory_edit, name='subcategory_edit'),
    path('subcategories/<int:pk>/delete/', views.subcategory_delete, name='subcategory_delete'),
    
    # Пользователи
    path('users/', views.user_list, name='user_list'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/toggle-services/', views.user_toggle_services, name='user_toggle_services'),
    path('users/<int:pk>/change-role/', views.user_change_role, name='user_change_role'),
    path('users/<int:pk>/verify/', views.user_verify, name='user_verify'),
]
