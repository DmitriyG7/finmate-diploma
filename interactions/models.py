from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.contrib.contenttypes.models import ContentType

from finmate import settings


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.BigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время лайка")

    class Meta:
        verbose_name = "Лайки"
        verbose_name_plural = "Лайки"

        constraints = [
            models.UniqueConstraint(
            fields=['user', 'content_type', 'object_id'],
            name='like_per_user_content_type_object_id'
            )
        ]

    def save(self, *args, **kwargs):
        obj = self.content_object

        author = getattr(obj, 'author', None) or getattr(obj, 'user', None)
        if author == self.user:
            raise ValueError("Вы не можете лайкать собственный контент")

        super().save(*args, **kwargs)