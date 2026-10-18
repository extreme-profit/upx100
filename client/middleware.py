import uuid


class VisitorIdentityMiddleware:
    cookie_name = 'booking_visitor'
    salt = 'client.booking.visitor'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw = request.get_signed_cookie(self.cookie_name, salt=self.salt, default='')
        try:
            request.booking_visitor = uuid.UUID(raw)
            fresh = False
        except (ValueError, TypeError, AttributeError):
            request.booking_visitor = uuid.uuid4()
            fresh = True
        response = self.get_response(request)
        if fresh and request.path.startswith('/client/'):
            response.set_signed_cookie(self.cookie_name, str(request.booking_visitor), salt=self.salt,
                                       max_age=31536000, httponly=True, secure=request.is_secure(), samesite='Lax')
        return response
