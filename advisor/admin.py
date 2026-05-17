from django.contrib import admin

from advisor.models import SavingGoal, GoalContribution


@admin.register(SavingGoal)
class SavingGoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "target_amount", "target_date", "status", "priority")
    list_filter = ("status", "priority")
    search_fields = ("title", "user__username")


@admin.register(GoalContribution)
class GoalContributionAdmin(admin.ModelAdmin):
    list_display = ("goal", "amount", "date")
    list_filter = ("date",)
    search_fields = ("goal__title", "goal__user__username")
