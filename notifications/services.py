from django.contrib.contenttypes.models import ContentType

from notifications.models import Notification


class NotificationsService:
    @staticmethod
    def create_notification(*, actor, recipient, verb, content_obj):
        if actor == recipient:
            return None

        note = Notification.objects.create(
            actor=actor,
            recipient=recipient,
            verb=verb,
            content_type=ContentType.objects.get_for_model(content_obj),
            object_id=content_obj.id
        )
        return note

    @staticmethod
    def delete_notification(*, actor, content_obj):
        ct = ContentType.objects.get_for_model(content_obj)
        Notification.objects.filter(
            actor = actor,
            object_id=content_obj.id,
            content_type=ct
        ).delete()