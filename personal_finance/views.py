from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .forms import TransactionUserForm, AddTransactionForm, UpdateTransactionForm, GraphicForm
from .models import PersonalTransaction, Category
from django.db.models import Sum, Count
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import timedelta


@login_required
def transaction_list(request):
    form = TransactionUserForm(data=request.GET or None)

    queryset = PersonalTransaction.objects.filter(user=request.user)\
        .select_related("category").order_by("-date", "-id")


    if form.is_valid():
        cd = form.cleaned_data
        today = timezone.now().date()

        # Обработка периода
        if cd["period"] == "day":
            queryset = queryset.filter(date=today)
        elif cd["period"] == "week":
            week_ago = today - timedelta(days=7)
            queryset = queryset.filter(date__gte=week_ago, date__lte=today)
        elif cd["period"] == "month":
            month_ago = today - timedelta(days=30)
            queryset = queryset.filter(date__gte=month_ago, date__lte=today)
        elif cd["period"] == "custom":
            queryset = queryset.filter(
                date__gte=cd["date_from"],
                date__lte=cd["date_to"]
            )

        # Тип операций
        if cd["operation_type"]:
            queryset = queryset.filter(operation_type=cd["operation_type"])

        # Категории
        categories = cd.get("category")
        if categories:
            queryset = queryset.filter(category__in=categories)

    context = {
        "form": form,
        "transactions": queryset,
        'title': 'Мои финансы',
    }

    return render(request, "personal_finance/transactions_list.html", context)


class AddTransaction(LoginRequiredMixin, CreateView):
    form_class = AddTransactionForm
    template_name = 'personal_finance/add_transaction.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.user = self.request.user
        return super().form_valid(form)


class UpdateTransaction(LoginRequiredMixin, UpdateView):
    model = PersonalTransaction
    form_class = UpdateTransactionForm
    template_name = 'personal_finance/edit_transaction.html'
    success_url = reverse_lazy('home')

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)


class DeleteTransaction(LoginRequiredMixin, DeleteView):
    model = PersonalTransaction
    success_url = reverse_lazy('home')

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)


@login_required
def analytics_view(request):
    form = GraphicForm(data=request.GET or None)
    queryset = (PersonalTransaction.objects.filter(user=request.user)
                .select_related("category").order_by("-date", "-id"))
    chart_data = []
    selected_categories_ids = []

    if form.is_valid():
        cd = form.cleaned_data
        today = timezone.now().date()

        # Обработка периода
        if cd["period"] == "day":
            queryset = queryset.filter(date=today)
        elif cd["period"] == "week":
            week_ago = today - timedelta(days=7)
            queryset = queryset.filter(date__gte=week_ago, date__lte=today)
        elif cd["period"] == "month":
            month_ago = today - timedelta(days=30)
            queryset = queryset.filter(date__gte=month_ago, date__lte=today)
        elif cd["period"] == "custom":
            queryset = queryset.filter(
                date__gte=cd["date_from"],
                date__lte=cd["date_to"]
            )

        # Тип операций
        if cd["operation_type"]:
            queryset = queryset.filter(operation_type=cd["operation_type"])

        # Категории
        active_categories = list(cd.get("category", []))
        selected_categories_ids = [cat.id for cat in active_categories]

        # Фильтрация по актуальным категориям
        if selected_categories_ids:
            queryset = queryset.filter(category__in=selected_categories_ids)

        aggregation_data = (
            queryset
            .values("category__name")
            .annotate(total=Sum("total"))
            .order_by("-total")
        )

        chart_data = [
            {"category": item["category__name"], "total": float(item["total"])}
            for item in aggregation_data
        ]

    context = {
        'user': request.user,
        'user_transactions': queryset,
        'chart_data': json.dumps(chart_data),
        'selected_category_ids': selected_categories_ids,
        'form': form,
    }

    return render(request, 'personal_finance/analytics.html', context)