from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from advisor.forms import SavingGoalForm, GoalContributionForm
from advisor.models import SavingGoal, GoalContribution
from advisor.services import AdvisorService


class SavingGoalListView(LoginRequiredMixin, ListView):
    model = SavingGoal
    template_name = "advisor/goal_list.html"
    context_object_name = "goals"

    def get_queryset(self):
        return SavingGoal.objects.filter(user=self.request.user).prefetch_related("contributions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        created_risk_notifications = AdvisorService.notify_goal_risks(user=self.request.user)
        # created_limit_notification = AdvisorService.notify_limit_control(user=self.request.user)
        if created_risk_notifications:
            messages.warning(
                self.request,
                f"Обнаружены риски по целям: {created_risk_notifications}. Проверь уведомления."
            )
        context["advice_cards"] = [
            AdvisorService.build_goal_advice(user=self.request.user, goal=goal)
            for goal in context["goals"]
            if goal.status in {SavingGoal.StatusType.ACTIVE, SavingGoal.StatusType.PAUSED}
        ]
        context["allocation_plan"] = AdvisorService.build_allocation_plan(user=self.request.user)
        context["title"] = "Финансовый советчик"
        return context


class SavingGoalCreateView(LoginRequiredMixin, CreateView):
    model = SavingGoal
    form_class = SavingGoalForm
    template_name = "advisor/goal_form.html"
    success_url = reverse_lazy("advisor:goal_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Цель накопления успешно создана.")
        return super().form_valid(form)


class SavingGoalUpdateView(LoginRequiredMixin, UpdateView):
    model = SavingGoal
    form_class = SavingGoalForm
    template_name = "advisor/goal_form.html"

    def get_queryset(self):
        return SavingGoal.objects.filter(user=self.request.user)

    def get_success_url(self):
        messages.success(self.request, "Цель обновлена.")
        return reverse_lazy("advisor:goal_detail", kwargs={"pk": self.object.pk})


class SavingGoalDetailView(LoginRequiredMixin, DetailView):
    model = SavingGoal
    template_name = "advisor/goal_detail.html"
    context_object_name = "goal"

    def get_queryset(self):
        return SavingGoal.objects.filter(user=self.request.user).prefetch_related("contributions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        advice = AdvisorService.build_goal_advice(user=self.request.user, goal=self.object)

        # ИЗМЕНЕНИЕ: Извлекаем фиксированные суммы из GET-запроса вместо процентов
        expense_cut_amount = self.request.GET.get("expense_cut_amount", "0.00")
        income_raise_amount = self.request.GET.get("income_raise_amount", "0.00")

        # Передаем обновленные именованные аргументы в метод сервиса
        scenario = AdvisorService.build_what_if(
            advice=advice,
            expense_cut_amount=expense_cut_amount,
            income_raise_amount=income_raise_amount,
        )

        context["advice"] = advice
        context["scenario"] = scenario
        context["contribution_form"] = GoalContributionForm(user=self.request.user)
        return context


class GoalContributionCreateView(LoginRequiredMixin, CreateView):
    model = GoalContribution
    form_class = GoalContributionForm
    http_method_names = ["post"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        goal = get_object_or_404(SavingGoal, pk=self.kwargs["pk"], user=self.request.user)
        cd = form.cleaned_data

        try:
            AdvisorService.make_goal_contribution(
                user=self.request.user,
                goal=goal,
                wallet_id=cd["wallet"].id,
                amount=cd["amount"],
                comment=cd["comment"],
                date=cd["date"]
            )
            messages.success(self.request, "Пополнение успешно добавлено, деньги списаны с кошелька.")
            return redirect(self.get_success_url())

        except ValidationError as e:
            messages.error(self.request, e.message)
            return redirect("advisor:goal_detail", pk=goal.pk)

    def get_success_url(self):
        return reverse_lazy("advisor:goal_detail", kwargs={"pk": self.kwargs["pk"]})