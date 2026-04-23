from django.urls import path
from . import views


urlpatterns = [
    path('', views.transaction_list, name='home'),
    path('add_transaction/', views.AddTransaction.as_view(), name='add_transaction'),
    path('edit_transaction/<int:pk>/', views.UpdateTransaction.as_view(), name='edit_transaction'),
    path('delete_transaction/<int:pk>/', views.DeleteTransaction.as_view(), name='delete_transaction'),

    path('analytics/', views.analytics_view, name='analytics'),

]