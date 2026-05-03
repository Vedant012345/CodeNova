"""
CodeNova v9 — Context Processors
Injects sidebar badge counts into every host template automatically.
No changes needed in individual views.
"""
from .models import ContactMessage, UserQuery


def host_sidebar_counts(request):
    """
    Provides unread contact message count and open query count for
    the host dashboard sidebar badges. Only runs DB queries when the
    user is authenticated as superuser (host panel users).
    """
    if request.user.is_authenticated and request.user.is_superuser:
        return {
            "new_contact_count": ContactMessage.objects.filter(status="new").count(),
            "open_query_count":  UserQuery.objects.filter(status="open").count(),
        }
    return {}
