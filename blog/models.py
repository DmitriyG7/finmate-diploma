import math

from django.db import models
from django.utils.text import slugify

from finmate import settings
from mdeditor.fields import MDTextField


class PostQuerySet(models.QuerySet):
    def verified(self):
        return self.filter(is_verified=True)

    def editorial(self):
        return self.filter(post_type=Post.PostType.EDITORIAL)

    def community(self):
        return self.filter(post_type=Post.PostType.COMMUNITY)


class Post(models.Model):
    class PostType(models.TextChoices):
        EDITORIAL = 'editorial', 'Редакция'
        COMMUNITY = 'community', 'Сообщество'

    title = models.CharField(max_length=255, verbose_name="Заголовок")
    slug = models.SlugField(unique=True, blank=True, db_index=True, verbose_name="Слаг статьи")
    content = MDTextField(verbose_name="Содержимое")
    post_type = models.CharField(max_length=50, choices=PostType.choices, default=PostType.COMMUNITY,
                                 db_index=True, verbose_name="Тип поста")
    is_verified = models.BooleanField(default=False, db_index=True, verbose_name="Одобрена")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")
    read_time = models.PositiveIntegerField(default=0)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="posts",
                               verbose_name="Автор")
    linked_category = models.ForeignKey("personal_finance.Category", on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name="posts", verbose_name="Связанная категория")

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = "Статья"
        verbose_name_plural = "Статьи"
        ordering=['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        self.read_time = self._calculate_read_time()
        super().save(*args, **kwargs)

    def _calculate_read_time(self):
        if not self.content:
            return 0

        word_count = len(self.content.split())
        minutes = word_count / 200

        return math.ceil(minutes) if  minutes > 0 else 1