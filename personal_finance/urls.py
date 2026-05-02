from django.urls import path
from . import views


urlpatterns = [
    path('', views.transaction_list, name='home'),
    path('add_transaction/', views.AddTransaction.as_view(), name='add_transaction'),
    path('edit_transaction/<int:pk>/', views.UpdateTransaction.as_view(), name='edit_transaction'),
    path('delete_transaction/<int:pk>/', views.DeleteTransaction.as_view(), name='delete_transaction'),
    path('transfer/', views.WalletTransferView.as_view(), name="wallet_transfer"),

    path('analytics/', views.analytics_view, name='analytics'),

    path('wallets/', views.UserWalletsList.as_view(), name='wallet_list'),
    path('wallets/create/', views.CreateWallet.as_view(), name='add_wallet'),
    path('wallets/<int:pk>/update/', views.WalletUpdateView.as_view(), name='update_wallet'),
    path('wallets/<int:pk>/delete/', views.WalletDeleteView.as_view(), name='delete_wallet'),

]