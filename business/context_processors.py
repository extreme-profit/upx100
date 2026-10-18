def billing_bell(request):
    if not request.path.startswith('/business/') or not request.user.is_authenticated or request.user.role != 'entrepreneur':
        return {}
    notifications = request.user.billing_notifications.all()
    return {'billing_unread_count':notifications.filter(read_at__isnull=True).count(),
            'billing_recent_notifications':notifications[:5]}
