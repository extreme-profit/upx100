from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from accounts.forms import FraudBlockForm
from accounts.models import FraudBlock, SecurityEvent, User
from accounts.security import confirm_fraud, lift_fraud, normalize_phone
from business.models import Company
from .views import admin_required


@admin_required
@never_cache
def blocked_users(request):
    q = request.GET.get('q', '').strip()[:200]
    state = request.GET.get('state', 'active')
    users = User.objects.filter(role='entrepreneur').filter(
        Q(is_active=False) | Q(company__is_blocked=True) | Q(company__fraud_blocked=True)
    ).select_related('company').order_by('-date_joined')
    blocks = FraudBlock.objects.select_related('company__owner','confirmed_by','lifted_by').prefetch_related('identifiers')
    attempts = SecurityEvent.objects.filter(action__in=['registration_blocked','service_blocked']).select_related('user','company','matched_block')
    if state != 'all':
        blocks = blocks.filter(lifted_at__isnull=True)
    if q:
        phone = normalize_phone(q)
        users = users.filter(Q(email__icontains=q) | Q(phone__icontains=q) | Q(company__name__icontains=q) | Q(company__phone__icontains=q))
        blocks = blocks.filter(Q(snapshot__owner__email__icontains=q) | Q(company__name__icontains=q) | Q(identifiers__value__icontains=q) | Q(identifiers__kind='phone', identifiers__value__icontains=phone or q)).distinct()
        attempts = attempts.filter(Q(email__icontains=q) | Q(phone__icontains=phone or q) | Q(ip__icontains=q))
    return render(request, 'dashboard/blocked_users.html', {
        'title':'Блокировки предпринимателей', 'q':q, 'state':state,
        'blocked_users':Paginator(users,20).get_page(request.GET.get('page')),
        'blocks':Paginator(blocks,20).get_page(request.GET.get('case_page')),
        'attempts':Paginator(attempts,20).get_page(request.GET.get('attempt_page')),
    })


@admin_required
@never_cache
def confirm_user_fraud(request, pk):
    company = get_object_or_404(Company.objects.select_related('owner'), owner_id=pk, owner__role='entrepreneur')
    form = FraudBlockForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            confirm_fraud(company, request.user, **{key:form.cleaned_data[key] for key in ['reason','evidence','extra_phones','extra_ips','block_ips']})
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Бессрочное ограничение сохранено. Все связанные услуги скрыты; повторные регистрации будут ограничены.')
            return redirect('dashboard:blocked_users')
    return render(request, 'dashboard/fraud_confirm.html', {
        'title':'Подтверждение антифрод-блокировки', 'company':company, 'form':form,
        'identity_events':company.owner.security_events.all()[:30],
    })


@admin_required
@require_POST
def lift_user_fraud(request, pk):
    get_object_or_404(FraudBlock, pk=pk)
    try:
        lift_fraud(pk, request.user, request.POST.get('reason',''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Антифрод-ограничение снято с учётом остальных действующих записей. Обычные блокировки сохранены.')
    return redirect('dashboard:blocked_users')


@admin_required
@never_cache
def export_fraud(request, pk):
    block = get_object_or_404(FraudBlock.objects.select_related('company__owner','confirmed_by','lifted_by'), pk=pk)
    response = JsonResponse({
        'block_id':block.pk, 'created_at':block.created_at, 'reason':block.reason, 'evidence':block.evidence,
        'confirmed_by':{'id':block.confirmed_by_id,'email':block.confirmed_by.email},
        'block_ips':block.block_ips, 'snapshot':block.snapshot,
        'identifiers':list(block.identifiers.values('kind','value')),
        'lifted_at':block.lifted_at, 'lifted_by_id':block.lifted_by_id, 'lift_reason':block.lift_reason,
        'events':list(SecurityEvent.objects.filter(Q(user_id=block.company.owner_id)|Q(matched_block=block)).values()),
    }, json_dumps_params={'ensure_ascii':False,'indent':2})
    response['Content-Disposition'] = f'attachment; filename="antifraud-{block.pk}.json"'
    response['Cache-Control'] = 'no-store'
    return response
