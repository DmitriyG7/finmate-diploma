from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns =[
    path('', views.NotificationListView.as_view(), name="list"),
    path("mark-as-read/<int:pk>/", views.MarkAsReadView.as_view(), name="mark_as_read"),
    path('mark-all-read/', views.MarkAllAsReadView.as_view(), name='mark_all_read'),
]