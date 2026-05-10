from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib import messages

from interactions.forms import CommentForm
from interactions.services import LikeService, CommentService


class LikeToggleView(LoginRequiredMixin, View):
    def post(self, request, model_name, object_id):
        ct = get_object_or_404(ContentType, model=model_name)

        obj = get_object_or_404(ct.model_class(), id=object_id)

        if not hasattr(obj, 'likes_count'):
            return JsonResponse({"error": "Эта модель не поддерживает лайки"}, status=400)

        author = getattr(obj, 'author', None) or getattr(obj, 'user', None)
        if author == request.user:
            return JsonResponse({'error': 'Нельзя лайкать самого себя'}, status=403)

        is_liked = LikeService.toggle_like(user=request.user, content_obj=obj)
        obj.refresh_from_db()
        return JsonResponse({'liked': is_liked, 'count': obj.likes_count})


class AddCommentView(LoginRequiredMixin, View):
    def post(self, request, model_name, object_id):
        ct = get_object_or_404(ContentType, model=model_name)
        obj = get_object_or_404(ct.model_class(), id=object_id)
        form = CommentForm(data=request.POST)

        if form.is_valid():
            text = form.cleaned_data.get('text')
            parent_id = request.POST.get('parent_id')
            comment = CommentService.add_comment(
                user=request.user,
                text=text,
                content_obj=obj,
                parent_id=parent_id
            )
            return JsonResponse({"status": "success", "comment_id": comment.id,
                                 "author": comment.author.username,
                                 "text": comment.text})

        return JsonResponse({"error": form.errors}, status=400)


class GetCommentsView(View):
    def get(self, request, model_name, object_id):
        offset = int(request.GET.get('offset', 0))
        limit = 10

        ct = get_object_or_404(ContentType, model=model_name)
        # Получаем только "родительские" комментарии (parent=None)
        comments = Comment.objects.filter(
            content_type=ct,
            object_id=object_id,
            parent=None
        ).select_related('author').prefetch_related('replies__author')[offset:offset + limit]

        # Генерируем HTML для этой пачки комментариев
        html = render_to_string('interactions/_comment_item.html', {
            'comments': comments,
            'user': request.user  # Передаем юзера для отображения кнопок
        }, request=request)

        return JsonResponse({
            'html': html,
            'has_more': comments.count() == limit
        })