from django.urls import path

from . import views

app_name = 'interactions'

urlpatterns = [
    path('like/<str:model_name>/<int:object_id>/', views.LikeToggleView.as_view(), name="like_toggle"),
    path('comments/add/<str:model_name>/<int:object_id>/', views.AddCommentView.as_view(), name="add_comment"),

    path('comments/get/<str:model_name>/<int:object_id>/', views.GetCommentsView.as_view(), name="get_comments"),
]