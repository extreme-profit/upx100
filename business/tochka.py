"""Tochka acquiring v1.0. No card data or credentials are persisted."""
import json
import ssl
from decimal import Decimal
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.urls import reverse


class TochkaError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TochkaClient:
    def __init__(self, environment=None):
        self.environment = environment or settings.TOCHKA_ENVIRONMENT
        if self.environment not in ('sandbox', 'live'):
            raise TochkaError('invalid_environment')
        if self.environment == 'live' and not settings.TOCHKA_LIVE_ENABLED:
            raise TochkaError('live_disabled')
        self.base = 'https://enter.tochka.com/' + ('sandbox/v2' if self.environment == 'sandbox' else 'uapi')
        self.token = 'sandbox.jwt.token' if self.environment == 'sandbox' else settings.TOCHKA_JWT_TOKEN
        self.customer = '1234567ab' if self.environment == 'sandbox' else settings.TOCHKA_CUSTOMER_CODE
        self.merchant = '200000000001097' if self.environment == 'sandbox' else settings.TOCHKA_MERCHANT_ID
        if not all([self.token, self.customer, self.merchant]):
            raise TochkaError('credentials_missing')

    def request(self, method, path, data=None):
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                          method=method, headers={'Authorization':'Bearer '+self.token, 'Accept':'application/json', 'Content-Type':'application/json'})
        context = ssl.create_default_context(cafile=settings.TOCHKA_CA_BUNDLE or None)
        opener = build_opener(HTTPSHandler(context=context), NoRedirect())
        try:
            with opener.open(request, timeout=15) as response:
                payload = json.loads(response.read(2*1024*1024))
            if not isinstance(payload.get('Data'), dict):
                raise TochkaError('invalid_response')
            return payload['Data']
        except HTTPError as exc:
            # Never include raw API responses, headers or tokens in logs/UI.
            raise TochkaError(f'http_{exc.code}') from None
        except (URLError, TimeoutError, OSError, ValueError, AttributeError):
            raise TochkaError('transport_or_response_error') from None

    def create(self, payment):
        invoice = payment.invoice
        return_url = settings.SITE_URL.rstrip('/') + reverse('business:invoice_detail', args=[invoice.pk])
        data = {'customerCode':self.customer, 'merchantId':self.merchant,
                'amount':format(payment.amount,'.2f'), 'purpose':f'Комиссия 42master.ru за {invoice.period:%m.%Y}, счёт {invoice.pk}',
                'paymentMode':['sbp','card'], 'preAuthorization':False, 'ttl':1440,
                'paymentLinkId':str(payment.pk), 'redirectUrl':return_url, 'failRedirectUrl':return_url}
        mode = settings.TOCHKA_RECEIPT_MODE or ('none' if self.environment == 'sandbox' else '')
        if mode not in ('none','bank'):
            raise TochkaError('receipt_mode_required')
        path = '/acquiring/v1.0/payments'
        if mode == 'bank':
            if settings.TOCHKA_TAX_SYSTEM not in ('osn','usn_income','usn_income_outcome','esn','patent') or not settings.TOCHKA_VAT_TYPE:
                raise TochkaError('receipt_settings_missing')
            data.update(taxSystemCode=settings.TOCHKA_TAX_SYSTEM,
                        Client={'name':invoice.company.name, 'email':invoice.company.owner.email},
                        Items=[{'name':f'Комиссия за услугу: {item.service_name}'[:256], 'amount':format(item.amount,'.2f'), 'quantity':1,
                                'vatType':settings.TOCHKA_VAT_TYPE, 'paymentMethod':'full_payment','paymentObject':'service'} for item in invoice.items.all()])
            if self.environment == 'sandbox':
                data['Client'] = {'name':'Тестовый предприниматель','email':'payments@example.com'}
            path += '_with_receipt'
        return self.request('POST', path, {'Data':data})

    def info(self, operation_id):
        # Provider IDs must never be interpreted as URL paths.
        from urllib.parse import quote
        return self.request('GET', '/acquiring/v1.0/payments/'+quote(operation_id, safe=''))
