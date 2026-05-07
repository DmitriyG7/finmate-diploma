from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F

from notifications.services import NotificationsService
from notifications.models import Notification
from .models import Like


class LikeService:
    @staticmethod
    def toggle_like(*, user, content_obj):
        ct = ContentType.objects.get_for_model(content_obj)

        with transaction.atomic():
            deleted_count, _ = Like.objects.filter(user=user, content_type=ct, object_id=content_obj.id).delete()

            if deleted_count > 0:
                type(content_obj).objects.filter(id=content_obj.id).update(likes_count=F('likes_count') - 1)
                NotificationsService.delete_notification(actor=user, content_obj=content_obj)
                return False
            else:
                Like.objects.create(user=user, content_type=ct, object_id=content_obj.id)
                type(content_obj).objects.filter(id=content_obj.id).update(likes_count=F("likes_count") + 1)
                author = getattr(content_obj, 'user', None) or getattr(content_obj, 'author', None)
                if author:
                    NotificationsService.create_notification(
                        recipient=author,
                        actor=user,
                        verb="лайкнул ваш пост",
                        content_obj=content_obj
                    )
                return True