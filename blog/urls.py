from django.urls import path

from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('post/create/', views.PostCreateView.as_view(), name='post_create'),
    path('post/<slug:slug>/', views.PostDetailView.as_view(), name='post_detail'),
    path('post/<slug:slug>/edit/', views.PostUpdateView.as_view(), name='post_update'),

    path('review/<int:pk>/', views.PostReviewDetailView.as_view(), name='post_review'),
    path('review/<int:pk>/approve/', views.PostApproveView.as_view(), name='approve_post'),

    path('my-posts/', views.UserPostListView.as_view(), name='user_posts'),
]