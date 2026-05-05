from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView, ListView, FormView
from django.urls import reverse_lazy
from django.views.generic.edit import ProcessFormView
from django.db import models

from .forms import TransactionUserForm, AddTransactionForm, UpdateTransactionForm, GraphicForm, CreateWalletForm, \
    UpdateWalletForm, TransferForm, CategoryForm
from .models import PersonalTransaction, Category, Wallet
from django.db.models import Sum, Count
import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from django.contrib import messages

import calendar
from datetime import timedelta, date

from personal_finance.services.finance_service import FinanceService


@login_required
def transaction_list(request):
    form = TransactionUserForm(data=request.GET or None, user=request.user)

    queryset = PersonalTransaction.objects.filter(user=request.user)\
        .select_related("category", "wallet").order_by("-date", "-id")

    selected_wallet = None
    if form.is_valid():
        cd = form.cleaned_data
        selected_wallet = cd.get("wallet")
        today = timezone.now().date()

        # Обработка периода
        if cd["period"] == "today":
            queryset = queryset.filter(date=today)

        elif cd["period"] == "week":
            week_ago = today - timedelta(days=7)
            queryset = queryset.filter(date__gte=week_ago, date__lte=today)

        elif cd["period"] == "month":
            start_date = today.replace(day=1) # 1-е число текущего месяца
            queryset = queryset.filter(date__gte=start_date, date__lte=today)

        elif cd["period"] == "last_month":
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            start_date = last_day_last_month.replace(day=1)
            queryset = queryset.filter(date__gte=start_date, date__lte=last_day_last_month)

        elif cd["period"] == "custom":
            if cd.get("date_from") and cd.get("date_to"):
                queryset = queryset.filter(
                    date__gte=cd["date_from"],
                    date__lte=cd["date_to"]
                )

        if cd["operation_type"]:
            queryset = queryset.filter(operation_type=cd["operation_type"])

        categories = cd.get("category")
        if categories:
            queryset = queryset.filter(category__in=categories)

        if cd.get("wallet"):
            queryset = queryset.filter(wallet=cd["wallet"])

    if 'wallet' not in request.GET:
        default_wallet = Wallet.objects.filter(user=request.user, is_default=True, is_active=True).first()
        if default_wallet:
            queryset = queryset.filter(wallet=default_wallet)
            form.initial['wallet'] = default_wallet.id
        elif selected_wallet:
            queryset = queryset.filter(wallet=selected_wallet)

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            FinanceService.create_transaction(
                user=self.request.user,
                wallet_id=cd["wallet"].id if cd.get("wallet") else None,
                amount=cd["total"],
                operation_type=cd["operation_type"],
                category=cd["category"],
                description=cd.get("description", ""),
                date = cd.get("date"),
            )

        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)
        return redirect(self.success_url)


class UpdateTransaction(LoginRequiredMixin, UpdateView):
    model = PersonalTransaction
    form_class = UpdateTransactionForm
    template_name = 'personal_finance/edit_transaction.html'
    success_url = reverse_lazy('home')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            FinanceService.update_transaction(
                transaction_obj=self.object,
                new_total=cd.get('total'),
                new_date=cd.get('date'),
                new_category=cd.get('category'),
                new_wallet=cd.get('wallet'),
                new_description=cd.get('description')
            )
            messages.success(self.request, "Транзакция успешно обновлена!")
        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)
        return redirect(self.success_url)


class DeleteTransaction(LoginRequiredMixin, DeleteView):
    model = PersonalTransaction
    success_url = reverse_lazy('home')

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)

    def form_valid(self, form):
        try:
            FinanceService.delete_transaction(
                transaction_obj=self.object
            )
            messages.success(self.request, "Транзакция успешно удалена, баланс обновлен")
        except ValidationError as e:
            messages.error(self.request, str(e))
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.success_url)


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
            {"category": item["category__name"], "total": float(item["total"] or 0)}
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

# -----------------------------------Wallets---------------------------

class CreateWallet(LoginRequiredMixin, CreateView):
    model = Wallet
    form_class = CreateWalletForm
    template_name='personal_finance/wallet_form.html'
    success_url = reverse_lazy('wallet_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        cd = form.cleaned_data
        try:
            FinanceService.create_wallet(
                user=self.request.user,
                name=cd["name"],
                wallet_type=cd["wallet_type"],
                balance=cd["balance"],
                currency=cd["currency"],
                is_default=cd["is_default"]
            )
            messages.success(self.request, f"Кошелек '{cd['name']}' успешно создан!")

        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)
        return redirect(self.success_url)


class WalletUpdateView(LoginRequiredMixin, UpdateView):
    model = Wallet
    form_class = UpdateWalletForm
    template_name = 'personal_finance/wallet_form.html'
    success_url = reverse_lazy('wallet_list')

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            FinanceService.update_wallet(
                wallet=self.object,
                name=cd["name"],
                is_default=cd["is_default"]
            )
            messages.success(self.request, f"Кошелек '{cd['name']}' успешно обновлен!")
        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, "message") else str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.success_url)


class WalletDeleteView(LoginRequiredMixin, DeleteView):
    model = Wallet
    success_url = reverse_lazy('wallet_list')

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        try:
            FinanceService.delete_wallet(
                wallet=self.object
            )
            messages.success(self.request, "Кошелек успешно удален.")
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.success_url)


class UserWalletsList(LoginRequiredMixin, ListView):
    model = Wallet
    context_object_name = 'wallets'
    template_name = 'personal_finance/wallets_list.html'
    paginate_by = 5

    def get_queryset(self):
        qs = (Wallet.objects.filter(user=self.request.user, is_active=True)
        .order_by('-is_default'))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_qs = self.get_queryset()
        total = full_qs.aggregate(total=Sum('balance'))['total']
        context['total_sum'] = total or 0
        return context


class WalletTransferView(LoginRequiredMixin, CreateView):
    form_class = TransferForm
    template_name = 'personal_finance/transfer.html'
    success_url = reverse_lazy('home')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            FinanceService.transfer(
                user=self.request.user,
                from_wallet_id=cd['from_wallet'].id,
                to_wallet_id=cd['to_wallet'].id,
                amount=cd["amount"]
            )
            messages.success(self.request, "Перевод успешно выполнен!")
        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, 'message') else str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.success_url)


# -----------------------------------Category------------------------------

class CategoryListView(LoginRequiredMixin, ListView, ProcessFormView):
    model = Category
    template_name = 'personal_finance/categories.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.for_user(user=self.request.user).annotate(
            transaction_count=Count(
                'category_transactions',
                filter=~models.Q(category_transactions__operation_type='transfer') &
                models.Q(category_transactions__user=self.request.user)
            )
        ).order_by('category_type', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = CategoryForm(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        form = CategoryForm(data=request.POST, user=request.user)

        if form.is_valid():
            try:
                FinanceService.create_category(
                    user=request.user,
                    name=form.cleaned_data['name'],
                    category_type=form.cleaned_data['category_type']
                )
                messages.success(request, "Категория успешно добавлена!")
                # Редирект на ту же страницу очищает POST-данные
                return redirect('category_list')
            except ValidationError as e:
                form.add_error(None, e.message)

        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'personal_finance/category_form.html'
    success_url = reverse_lazy('category_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        cd = form.cleaned_data

        try:
            FinanceService.update_category(
                category_obj=self.object,
                user=self.request.user,
                name=cd.get('name'),
                new_type=cd.get('category_type')
            )
            messages.success(self.request, "Категория успешно изменена!")
            return redirect(self.success_url)
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    success_url = reverse_lazy('category_list')

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user, is_active=True)

    def form_valid(self, form):
        try:
            FinanceService.delete_category(
                category_obj=self.object,
                user=self.request.user
            )
            messages.success(self.request, "Категория успешно удалена!")
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"Ошибка операции: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.success_url)