from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F

from notifications.services import NotificationsService
from notifications.models import Notification
from .models import Like, Comment


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


class CommentService:
    @staticmethod
    def add_comment(*, user, text, content_obj, parent_id=None):
        with transaction.atomic():
            ct = ContentType.objects.get_for_model(content_obj)
            comment = Comment.objects.create(
                author=user,
                text=text,
                content_type=ct,
                object_id=content_obj.id,
                parent_id=parent_id
            )

            post_author = getattr(content_obj, 'author', None) or getattr(content_obj, 'user', None)
            if post_author and parent_id is None:
                NotificationsService.create_notification(
                    actor=user,
                    recipient=post_author,
                    verb='оставил комментарий',
                    content_obj=content_obj
                )

            if parent_id is not None:
                try:
                    parent_comment = Comment.objects.select_related('author').get(id=parent_id)
                    if parent_comment.author != user:
                        NotificationsService.create_notification(
                            actor=user,
                            recipient=parent_comment.author,
                            verb='ответил на ваш комментарий',
                            content_obj=content_obj
                        )
                except Comment.DoesNotExist:
                    raise ValueError("Комментарий не существует")

            return comment