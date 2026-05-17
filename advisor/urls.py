from django.urls import path

from advisor import views

app_name = "advisor"

urlpatterns = [
    path("", views.SavingGoalListView.as_view(), name="goal_list"),
    path("goals/create/", views.SavingGoalCreateView.as_view(), name="goal_create"),
    path("goals/<int:pk>/", views.SavingGoalDetailView.as_view(), name="goal_detail"),
    path("goals/<int:pk>/edit/", views.SavingGoalUpdateView.as_view(), name="goal_update"),
    path("goals/<int:pk>/contributions/add/", views.GoalContributionCreateView.as_view(), name="add_contribution"),
]
