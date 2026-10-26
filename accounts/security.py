"""Owner anti-fraud decisions and append-only identity observations."""
import ipaddress
import json
import unicodedata
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import FraudBlock, FraudIdentifier, SecurityEvent, User

SUPPORT = 'http://6max.ru/admin_extreme_profit'
BLOCK_MESSAGE = 'Публикация новых услуг недоступна. Для проверки ограничений обратитесь в поддержку: ' + SUPPORT
HISTORY_ACTIONS = ['registered', 'registration_blocked', 'login', 'service_saved', 'profile_saved']


def normalize_phone(value):
    value = ''.join(str(unicodedata.decimal(char)) for char in str(value or '') if char.isdecimal())
    if value.startswith('00'):
        value = value[2:]
    if len(value) == 11 and value.startswith('8'):
        value = '7' + value[1:]
    if len(value) == 10:
        value = '7' + value
    return value


def valid_phone(value):
    return 10 <= len(normalize_phone(value)) <= 15


def remote_ip(request):
    try:
        peer = ipaddress.ip_address(request.META.get('REMOTE_ADDR', ''))
        networks = [ipaddress.ip_network(value) for value in getattr(settings, 'ANTIFRAUD_TRUSTED_PROXY_CIDRS', [])]
        trusted = lambda address: any(address in network for network in networks)
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if trusted(peer) and forwarded and len(forwarded) <= 2048:
            chain = [ipaddress.ip_address(value.strip()) for value in forwarded.split(',')]
            if len(chain) <= 20:
                for address in reversed(chain + [peer]):
                    if not trusted(address):
                        return str(address)
        return str(peer)
    except ValueError:
        # Invalid proxy headers must not erase a valid directly observed peer.
        try:
            return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
        except ValueError:
            return None


def public_ip(value):
    try:
        address = ipaddress.ip_address(value or '')
        return str(address) if address.is_global else None
    except ValueError:
        return None


def identity_phones(user, company=None):
    phones = {normalize_phone(user.phone)}
    if company:
        phones.add(normalize_phone(company.phone))
    for phone, company_phone in user.security_events.filter(action__in=HISTORY_ACTIONS).values_list('phone', 'company_phone'):
        phones.update([phone, company_phone])
    return {phone for phone in phones if valid_phone(phone)}


def find_block(phones=(), ip=None, user=None, company=None):
    phones = {normalize_phone(value) for value in phones if valid_phone(value)}
    query = Q(identifiers__kind='phone', identifiers__value__in=phones)
    if public_ip(ip):
        query |= Q(block_ips=True, identifiers__kind='ip', identifiers__value=public_ip(ip))
    if user and user.pk:
        phones |= identity_phones(user, company)
        query |= Q(company__owner_id=user.pk)
        query |= Q(identifiers__kind='phone', identifiers__value__in=phones)
        query |= Q(events__user_id=user.pk, events__action__in=['registration_blocked','service_blocked'])
    return FraudBlock.objects.filter(lifted_at__isnull=True).filter(query).distinct().first()


def record_event(request, user, company, action, block=None):
    event = SecurityEvent.objects.create(
        user=user, company=company, matched_block=block, action=action,
        email=user.email, phone=normalize_phone(user.phone),
        company_phone=normalize_phone(company.phone) if company else '',
        ip=remote_ip(request), snapshot={
            'name': user.get_full_name(), 'raw_phone': user.phone,
            'company_name': company.name if company else '',
            'company_phone': company.phone if company else '',
            'address': company.address if company else '',
        },
    )
    if action == 'registration_blocked':
        from business.notifications import queue_email
        for admin in User.objects.filter(is_active=True).filter(Q(role='admin') | Q(is_superuser=True)):
            if admin.email:
                queue_email(f'antifraud:{event.pk}:admin:{admin.pk}', admin.email,
                    'Повторная регистрация заблокированного исполнителя',
                    f'Аккаунт №{user.pk} зарегистрирован с ограничением публикации.\n'
                    f'Компания: {company.name}\nEmail: {user.email}\nТелефон: {event.phone}\nIP: {event.ip or "Не определён"}\n'
                    f'Совпадение с записью антифрод-реестра №{block.pk}.\n'
                    f'{settings.SITE_URL.rstrip("/")}/dashboard/blocks/')
    return event


def enforce_service_restriction(request, company):
    block = find_block(ip=remote_ip(request), user=company.owner, company=company)
    if block:
        from business.models import Company
        Company.objects.filter(pk=company.pk).update(fraud_blocked=True)
        company.fraud_blocked = True
    if block or company.fraud_blocked:
        record_event(request, company.owner, company, 'service_blocked', block)
        return True
    return False


def require_admin(actor):
    if not actor.is_active or not (actor.is_superuser or actor.role == 'admin'):
        raise PermissionDenied


def refresh_fraud_flags():
    from business.models import Company
    active = FraudBlock.objects.filter(lifted_at__isnull=True)
    identifiers = FraudIdentifier.objects.filter(block__in=active)
    phones = set(identifiers.filter(kind='phone').values_list('value', flat=True))
    ips = set(identifiers.filter(kind='ip', block__block_ips=True).values_list('value', flat=True))
    users = set(active.values_list('company__owner_id', flat=True))
    observations = SecurityEvent.objects.filter(action__in=HISTORY_ACTIONS)
    users.update(observations.filter(Q(phone__in=phones) | Q(company_phone__in=phones) | Q(ip__in=ips)).values_list('user_id', flat=True))
    users.update(SecurityEvent.objects.filter(action__in=['registration_blocked','service_blocked'], matched_block__in=active).values_list('user_id', flat=True))
    blocked = []
    for company in Company.objects.select_related('owner').iterator():
        if company.owner_id in users or normalize_phone(company.phone) in phones or normalize_phone(company.owner.phone) in phones:
            blocked.append(company.pk)
    Company.objects.filter(pk__in=blocked).update(fraud_blocked=True)
    Company.objects.filter(fraud_blocked=True).exclude(pk__in=blocked).update(fraud_blocked=False)


@transaction.atomic
def confirm_fraud(company, actor, reason, evidence='', extra_phones=(), extra_ips=(), block_ips=True):
    from business.models import Company
    require_admin(actor)
    company = Company.objects.select_for_update().select_related('owner').get(pk=company.pk)
    if company.owner.role != 'entrepreneur':
        raise ValidationError('В реестр можно добавить только предпринимателя.')
    if not reason.strip() or len(reason) > 4000 or len(evidence) > 10000:
        raise ValidationError('Укажите причину до 4000 символов; материалы — до 10000 символов.')
    if company.fraud_blocks.filter(lifted_at__isnull=True).exists():
        raise ValidationError('У компании уже есть действующая запись в реестре.')
    phones = identity_phones(company.owner, company)
    for value in extra_phones:
        if not valid_phone(value):
            raise ValidationError('Проверьте дополнительный телефон.')
        phones.add(normalize_phone(value))
    ips = {public_ip(value) for value in company.owner.security_events.values_list('ip', flat=True)}
    for value in extra_ips:
        if not public_ip(value):
            raise ValidationError('Для блокировки IP укажите публичный адрес.')
        ips.add(public_ip(value))
    ips.discard(None)
    snapshot = {
        'owner': {'id':company.owner_id, 'email':company.owner.email, 'name':company.owner.get_full_name(),
                  'phone':company.owner.phone, 'registered_at':company.owner.date_joined},
        'company': {'id':company.pk, 'name':company.name, 'phone':company.phone, 'email':company.email,
                    'address':company.address, 'city':company.city, 'time_zone':company.time_zone},
        'services':list(company.services.values('id','name','description','price','delivery_mode','is_archived')),
        'employees':list(company.employees.values('id','user__email','user__first_name','user__last_name','phone')),
    }
    snapshot = json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))
    block = FraudBlock.objects.create(company=company, confirmed_by=actor, reason=reason.strip(),
        evidence=evidence.strip(), snapshot=snapshot, block_ips=block_ips)
    FraudIdentifier.objects.bulk_create([FraudIdentifier(block=block,kind=kind,value=value)
        for kind,values in [('phone',phones),('ip',ips)] for value in sorted(values)])
    refresh_fraud_flags()
    return block


@transaction.atomic
def lift_fraud(block_id, actor, reason):
    require_admin(actor)
    if not reason.strip() or len(reason)>4000:
        raise ValidationError('Укажите причину снятия ограничения (до 4000 символов).')
    block = FraudBlock.objects.select_for_update().get(pk=block_id)
    if block.lifted_at:
        return block
    block.lifted_at, block.lifted_by, block.lift_reason = timezone.now(), actor, reason.strip()
    block.save(update_fields=['lifted_at','lifted_by','lift_reason'])
    refresh_fraud_flags()
    return block
