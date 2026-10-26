from django.http import Http404
from django.shortcuts import get_object_or_404
from .models import Service


def service_for_user(user, service_id):
    company = user.get_company()
    if not company:
        raise Http404('Услуга не найдена')
    services = Service.objects.filter(company=company)
    if user.role == 'employee':
        employee = user.get_employee_profile()
        if not employee or not employee.is_active:
            raise Http404('Услуга не найдена')
        services = services.filter(employees=employee)
    elif company.owner_id != user.pk:
        raise Http404('Услуга не найдена')
    return get_object_or_404(services, pk=service_id)


def schedule_employees(user, service):
    employees = service.employees.filter(is_active=True, company_id=service.company_id)
    if user.role == 'employee':
        employees = employees.filter(user=user)
    return employees


def employee_for_request(user, service, requested=None):
    allowed = schedule_employees(user, service)
    if requested in (None, ''):
        return allowed.get(user=user).pk if user.role == 'employee' else None
    try:
        employee_id = int(requested)
    except (ValueError, TypeError):
        raise Http404('Сотрудник не найден')
    if not allowed.filter(pk=employee_id).exists():
        raise Http404('Сотрудник не найден')
    return employee_id
