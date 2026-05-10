from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.exceptions import PermissionDenied

from notifications.services import NotificationsService
from personal_finance.models import Category
from .models import Post


class PostService:
    @staticmethod
    def create_post(*, author, title, content, post_type, status, linked_category):
        with transaction.atomic():
            if not author.is_staff:
                if post_type != Post.PostType.COMMUNITY:
                    raise PermissionDenied("У вас недостаточно прав")
                if status == Post.StatusType.PUBLISHED:
                    raise PermissionDenied("Опубликовать статью может только администратор")

            if linked_category:
                category = Category.objects.base_categories().filter(id=linked_category.id).first()
                if not category:
                    raise ValidationError("Категория не найдена")

            post = Post.objects.create(
                author=author,
                title=title,
                post_type=post_type,
                status=status,
                linked_category=linked_category,
                is_verified=True if author.is_staff else False,
                content=content
            )
            if post_type == Post.PostType.COMMUNITY and status == Post.StatusType.CHECKING:
                NotificationsService.notify_admins(
                    post=post,
                    verb=f"отправил новую статью на проверку: '{post.title}'",
                    actor=author
                )
            return post

    @staticmethod
    def update_post(*, user, post_obj, title=None, content=None, post_type=None, status=None, linked_category=None):
        with transaction.atomic():
            post_obj = Post.objects.select_for_update().get(author=post_obj.author, id=post_obj.id)

            if not (user.is_staff or post_obj.author == user):
                raise PermissionDenied("У вас недостаточно прав")

            if post_obj.status == Post.StatusType.CHECKING and not user.is_staff:
                raise ValidationError("Ваша статья на проверке. Дождитесь окончания модерации")

            new_title = title if title is not None else post_obj.title
            new_content = content if content is not None else post_obj.content
            new_status = status if status is not None else post_obj.status
            new_post_type = post_type if post_type is not None else post_obj.post_type
            new_linked_category = linked_category if linked_category is not None else post_obj.linked_category

            if new_linked_category is not None:
                category_exists = Category.objects.base_categories().filter(id=new_linked_category.id).exists()
                if not category_exists:
                    raise ValidationError("Категории не существует или она недоступна")


            if not user.is_staff and post_obj.status == Post.StatusType.PUBLISHED:
                changes = {}
                messages = []

                if new_title != post_obj.title:
                    changes['title'] = new_title
                    messages.append(f"Изменен заголовок статьи c {post_obj.title} на {new_title}")

                if new_content != post_obj.content:
                    changes['content'] = new_content
                    messages.append("Изменено содержание статьи")

                if new_linked_category != post_obj.linked_category:
                    changes['linked_category'] = new_linked_category.id if new_linked_category else None
                    messages.append(f"Изменена категория статьи с {post_obj.linked_category} на {new_linked_category}")

                if changes:
                    post_obj.pending_revision = changes
                    post_obj.has_unreviewed_changes = True
                    post_obj.save()
                    NotificationsService.notify_admins(
                        post=post_obj,
                        verb=f"Пользователь {post_obj.author.username} хочет изменить статью",
                        actor=user
                    )
                    return post_obj

            if post_obj.status == Post.StatusType.DRAFT and new_status == Post.StatusType.CHECKING:
                NotificationsService.notify_admins(
                    post=post_obj,
                    verb=f"отправил новую статью на проверку: '{post_obj.title}'",
                    actor=user
                )

            post_obj.title = new_title
            post_obj.content = new_content
            post_obj.status = new_status
            post_obj.linked_category = new_linked_category
            post_obj.post_type = new_post_type

            if user.is_staff:
                post_obj.has_unreviewed_changes = False
                post_obj.pending_revision = {}
                if new_status == Post.StatusType.PUBLISHED:
                    post_obj.is_verified = True

            post_obj.save()
            return post_obj

    @staticmethod
    def delete_post(*, user, post_obj):
        if post_obj.author != user and not user.is_staff:
            raise PermissionDenied("Вы не можете удалить чужую статью")

        post_obj.delete()

    @staticmethod
    def approve_revision(*, user, post_obj):
        if not user.is_staff:
            raise PermissionDenied("Только модератор может одобрять правки")

        with transaction.atomic():
            post_obj = Post.objects.select_for_update().get(id=post_obj.id)

            if not post_obj.has_unreviewed_changes:
                raise ValidationError("У этой статьи нет правок для одобрения")

            changes = post_obj.pending_revision

            if 'title' in changes:
                post_obj.title = changes['title']
            if 'content' in changes:
                post_obj.content = changes['content']
            if 'linked_category' in changes:
                if changes['linked_category'] is None:
                    post_obj.linked_category = None
                else:
                    category = Category.objects.get(id=changes['linked_category'])
                    post_obj.linked_category = category

            post_obj.pending_revision = {}
            post_obj.has_unreviewed_changes = False
            post_obj.is_verified = True

            post_obj.save()

            NotificationsService.create_notification(
                recipient=post_obj.author,
                actor=user,
                verb=f"Ваши изменения в статье '{post_obj.title}' были опубликованы.",
                content_obj=post_obj
            )

            return post_obj