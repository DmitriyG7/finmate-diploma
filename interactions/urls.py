from django.urls import path

from . import views

app_name = 'interactions'

urlpatterns = [
    path('like/<str:model_name>/<int:object_id>/', views.LikeToggleView.as_view(), name="like_toggle"),

]