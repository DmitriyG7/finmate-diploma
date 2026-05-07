from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F
from .models import Like


class LikeService:
    @staticmethod
    def toggle_like(*, user, content_obj):
        ct = ContentType.objects.get_for_model(content_obj)

        with transaction.atomic():
            deleted_count, _ = Like.objects.filter(user=user, content_type=ct, object_id=content_obj.id).delete()

            if deleted_count > 0:
                type(content_obj).objects.filter(id=content_obj.id).update(likes_count=F('likes_count') - 1)
                return False
            else:
                Like.objects.create(user=user, content_type=ct, object_id=content_obj.id)
                type(content_obj).objects.filter(id=content_obj.id).update(likes_count=F("likes_count") + 1)
                return True