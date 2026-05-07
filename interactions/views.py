from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views import View

from interactions.services import LikeService


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