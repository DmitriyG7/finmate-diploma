from .models import Notification


def unread_notifications(request):
    if request.user.is_authenticated:
        note_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {"unread_notifications_count": note_count}
    return {"unread_notifications_count": 0}