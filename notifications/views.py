from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.views.generic import ListView
from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "notifications/notification_list.html"
    paginate_by = 10

    def get_queryset(self):
        qs = Notification.objects.select_related('actor', 'content_type').filter(recipient=self.request.user)
        return qs


class MarkAsReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, recipient=request.user, pk=pk)
        notification.is_read = True
        notification.save()

        return JsonResponse({"status": "success"})


class MarkAllAsReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({"status": "success"})