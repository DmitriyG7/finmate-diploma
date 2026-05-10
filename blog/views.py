from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.db.models import Sum, OuterRef, Exists, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView

import logging
import difflib
from django.utils.safestring import mark_safe

from blog.forms import PostForm
from blog.models import Post
from blog.services import PostService
from interactions.forms import CommentForm
from interactions.models import Like
from personal_finance.models import PersonalTransaction

logger = logging.getLogger(__name__)


class PostListView(LoginRequiredMixin, ListView):
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        queryset = Post.objects.verified().select_related('author', 'linked_category')
        user = self.request.user

        if user and user.is_authenticated:
            user_likes = Like.objects.filter(
                content_type=ContentType.objects.get_for_model(Post),
                object_id=OuterRef('pk'),
                user=user
            )
            queryset = queryset.annotate(user_liked=Exists(user_likes))

        return queryset


class PostDetailView(LoginRequiredMixin, DetailView):
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Post.objects.all()

        return Post.objects.filter(
            Q(is_verified=True, status=Post.StatusType.PUBLISHED) | Q(author=user)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        comments_qs = self.object.comments.filter(parent=None).select_related("author").prefetch_related("replies__author")
        context['comments'] = comments_qs[:10]
        context['has_more_comments'] = comments_qs.count() > 10

        if self.request.user and self.request.user.is_authenticated and post.linked_category:
            start_month = timezone.now().replace(day=1, hour=0, minute=0, second=0)

            total_spent = PersonalTransaction.objects.filter(
                user=self.request.user,
                operation_type='expense',
                category=post.linked_category,
                date__gte=start_month
            ).aggregate(total_sum=Sum("total"))['total_sum'] or 0

            context['user_liked'] = Like.objects.filter(
                user=self.request.user,
                content_type=ContentType.objects.get_for_model(post),
                object_id=post.id
            ).exists()
            context['user_category_spent'] = total_spent
        context['comment_form'] = CommentForm()
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = "blog/post_form.html"
    success_url = reverse_lazy("blog:post_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            PostService.create_post(
                author=self.request.user,
                title=cd.get('title'),
                content=cd.get('content'),
                post_type=cd.get('post_type'),
                status=cd.get('status'),
                linked_category=cd.get('linked_category')
            )
            messages.success(self.request, "Статья отправлена на модерацию!")
        except PermissionDenied as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except Exception as e:
            logger.exception("Unexpected error while creating post")
            form.add_error(None, "Произошла непредвиденная ошибка. Попробуйте позже.")
            return self.form_invalid(form)
        return redirect(self.success_url)


class PostUpdateView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/post_form.html'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Post.objects.all()
        return Post.objects.filter(author=self.request.user)

    def get_form_kwargs(self):
        kwargs =super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            PostService.update_post(
                user=self.request.user,
                post_obj=self.object,
                **form.cleaned_data
            )
            messages.success(self.request, "Изменения сохранены или отправлены на модерацию!")
            return redirect(self.get_success_url())
        except (PermissionDenied,  ValidationError) as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)

        except Exception as e:
            logger.exception("Unexpected error while updating post")
            form.add_error(None, "Произошла непредвиденная ошибка. Попробуйте позже.")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('blog:post_detail', kwargs={'slug': self.object.slug})


class PostReviewDetailView(LoginRequiredMixin, DetailView):
    model = Post
    template_name = 'blog/post_review.html'
    context_object_name = 'post'

    def get_queryset(self):
        return Post.objects.filter(has_unreviewed_changes=True)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        pending = post.pending_revision

        if 'content' in pending:
            d = difflib.HtmlDiff()
            diff_html = d.make_table(
                post.content.splitlines(),
                pending['content'].splitlines(),
                fromdesc="Текущий текст",
                todesc="Новая правка"
            )
            context['content_diff'] = mark_safe(diff_html)

        return context


class PostApproveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied

        try:
            post = Post.objects.get(pk=pk)
        except Post.DoesNotExist as e:
            raise Http404("Статья не найдена") from e

        try:
            PostService.approve_revision(user=request.user, post_obj=post)
            messages.success(request, "Правки успешно применены!")
        except (PermissionDenied, ValidationError) as e:
            messages.error(request, f"Ошибка: {e}")
        except Exception as e:
            logger.exception("Unexpected error while approving post revision")
            messages.error(request, "Произошла непредвиденная ошибка. Попробуйте позже.")

        return redirect('blog:post_list')


class UserPostListView(LoginRequiredMixin, ListView):
    model = Post
    template_name = 'blog/user_posts.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Post.objects.filter(
                Q(author=user) |
                Q(status=Post.StatusType.CHECKING) |
                Q(has_unreviewed_changes=True)
            ).distinct().order_by('-created_at')
        return Post.objects.filter(author=user).order_by('-created_at')