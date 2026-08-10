from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView, ListView, FormView, View
from django.urls import reverse_lazy
from django.views.generic.edit import ProcessFormView
from django.db import models

from .forms import TransactionUserForm, AddTransactionForm, UpdateTransactionForm, GraphicForm, CreateWalletForm, \
    UpdateWalletForm, TransferForm, CategoryForm, WalletShareInviteForm
from .models import PersonalTransaction, Category, CategoryLimit, Wallet, WalletShareInvite, WalletMember, OperationType, CategoryLimit
from django.db.models import Sum, Count, Avg, Q, Subquery, Value, OuterRef
import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

import calendar
from datetime import timedelta, date

from personal_finance.services.finance_service import FinanceService
from blog.models import Post
from notifications.services import NotificationsService


@login_required
def transaction_list(request):
    relevant_post = None
    today = timezone.now().date()

    filter_params = request.GET.copy()
    if 'period' not in filter_params:
        filter_params['period'] = 'month'

    if 'wallet' not in filter_params:
        default_wallet = Wallet.objects.filter(user=request.user, is_default=True, is_active=True).first()
        if default_wallet:
            filter_params['wallet'] = default_wallet.id

    form = TransactionUserForm(data=filter_params, user=request.user)
    accessible_wallets = Wallet.accessible_for_user(request.user)

    queryset = PersonalTransaction.objects.filter(wallet__in=accessible_wallets) \
        .select_related("category", "wallet", "performed_by").order_by("-date", "-id")

    totals_queryset = PersonalTransaction.objects.filter(wallet__in=accessible_wallets)

    if form.is_valid():
        cd = form.cleaned_data

        if cd["period"] == "today":
            queryset = queryset.filter(date=today)
            totals_queryset = totals_queryset.filter(date=today)

        elif cd["period"] == "week":
            week_ago = today - timedelta(days=7)
            queryset = queryset.filter(date__gte=week_ago, date__lte=today)
            totals_queryset = totals_queryset.filter(date__gte=week_ago, date__lte=today)

        elif cd["period"] == "month":
            start_date = today.replace(day=1)
            queryset = queryset.filter(date__gte=start_date, date__lte=today)
            totals_queryset = totals_queryset.filter(date__gte=start_date, date__lte=today)

        elif cd["period"] == "last_month":
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            start_date = last_day_last_month.replace(day=1)
            queryset = queryset.filter(date__gte=start_date, date__lte=last_day_last_month)
            totals_queryset = totals_queryset.filter(date__gte=start_date, date__lte=last_day_last_month)

        elif cd["period"] == "custom" and cd.get("date_from") and cd.get("date_to"):
            queryset = queryset.filter(date__gte=cd["date_from"], date__lte=cd["date_to"])
            totals_queryset = totals_queryset.filter(date__gte=cd["date_from"], date__lte=cd["date_to"])

        if cd.get("wallet"):
            queryset = queryset.filter(wallet=cd["wallet"])
            totals_queryset = totals_queryset.filter(wallet=cd["wallet"])

        if cd["operation_type"]:
            queryset = queryset.filter(operation_type=cd["operation_type"])

        categories = cd.get("category")
        if categories:
            queryset = queryset.filter(category__in=categories)
            relevant_post = Post.objects.verified().filter(linked_category=categories[0]).first()

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    daily_map = {}
    for transaction in page_obj:
        tx_date = transaction.date
        if tx_date not in daily_map:
            daily_map[tx_date] = {
                "date": tx_date,
                "income": Decimal("0.00"),
                "expense": Decimal("0.00"),
                "transactions": []
            }
        day_data = daily_map[tx_date]
        day_data["transactions"].append(transaction)

        if transaction.operation_type == OperationType.INCOME:
            day_data["income"] += transaction.total
        elif transaction.operation_type == OperationType.EXPENSE:
            day_data["expense"] += transaction.total

    grouped_transactions = list(daily_map.values())

    totals = totals_queryset.aggregate(
        total_income=Sum('total', filter=Q(operation_type=OperationType.INCOME)),
        total_expense=Sum('total', filter=Q(operation_type=OperationType.EXPENSE))
    )

    period_income = totals['total_income'] or Decimal('0.00')
    period_expense = totals['total_expense'] or Decimal('0.00')

    total_balance = Wallet.objects.filter(id__in=accessible_wallets).aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0.00')

    context = {
        "form": form,
        "transactions": page_obj,
        "title": 'Мои финансы',
        "relevant_post": relevant_post,
        "transactions_grouped": grouped_transactions,
        "user_wallets": accessible_wallets,

        # Дашборд теперь всегда показывает корректные данные за весь период
        "total_balance": total_balance,
        "period_income": period_income,
        "period_expense": period_expense,
    }

    if request.headers.get('HX-Request'):
        return render(request, "personal_finance/partials/transaction_items.html", context)

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
            messages.success(self.request, "Транзакция создана!")
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

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)

        if obj.category and obj.category.name == "Накопления":
            raise PermissionDenied(
                "Редактирование автоматических транзакций накоплений запрещено. "
                "Изменения вносятся только через финансовые цели."
            )
        return obj

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
    filter_params = request.GET.copy()

    if 'period' not in filter_params:
        filter_params['period'] = 'month'

    if 'operation_type' not in filter_params:
        filter_params['operation_type'] = 'expense'

    if 'wallet' not in filter_params:
        default_wallet = Wallet.objects.filter(user=request.user, is_active=True, is_default=True).first()
        if default_wallet:
            filter_params['wallet'] = default_wallet.id

    form = GraphicForm(user=request.user, data=filter_params)
    accessible_wallets = Wallet.accessible_for_user(request.user)

    chart_data = []
    chart_timeline = []
    selected_categories_ids = []

    metrics = {
        'total_sum': 0,
        'total_count': 0,
        'avg_check': 0,
        'top_category': None,
        'sum_trend': None,
        'count_trend': None,
        'avg_check_trend': None,
        'sum_trend_color': "",
        'count_trend_color': "",
        'avg_trend_color': ""
    }

    # Инициализируем пустой базовый кверисет
    queryset = PersonalTransaction.objects.filter(wallet__in=accessible_wallets)

    if form.is_valid():
        cd = form.cleaned_data
        today = timezone.now().date()

        # Точная синхронизация периодов с вашей transaction_list + расчет прошлых периодов для трендов
        if cd["period"] in ["day", "today"]:
            start_date = end_date = today
            prev_start_date = prev_end_date = today - timedelta(days=1)

        elif cd["period"] == "week":
            week_ago = today - timedelta(days=7)
            start_date = week_ago
            end_date = today
            # Прошлая неделя для сравнения
            prev_end_date = start_date - timedelta(days=1)
            prev_start_date = prev_end_date - timedelta(days=7)

        elif cd["period"] == "month":
            start_date = today.replace(day=1)
            end_date = today
            # Прошлый месяц (текущий срез MTD для честного сравнения)
            last_day_last_month = start_date - timedelta(days=1)
            prev_start_date = last_day_last_month.replace(day=1)
            try:
                prev_end_date = prev_start_date.replace(day=today.day)
            except ValueError:
                prev_end_date = last_day_last_month

        elif cd["period"] == "last_month":
            # Чистый прошлый календарный месяц из вашей transaction_list
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            start_date = last_day_last_month.replace(day=1)
            end_date = last_day_last_month

            # Месяц, предшествующий прошлому (для тренда)
            last_day_month_before = start_date - timedelta(days=1)
            prev_start_date = last_day_month_before.replace(day=1)
            prev_end_date = last_day_month_before

        elif cd["period"] == "custom" and cd.get("date_from") and cd.get("date_to"):
            start_date = cd["date_from"]
            end_date = cd["date_to"]
            # Сдвиг назад на такое же количество дней для кастомного периода
            delta = (end_date - start_date).days + 1
            prev_end_date = start_date - timedelta(days=1)
            prev_start_date = prev_end_date - timedelta(days=max(0, delta - 1))
        else:
            # Фолбэк, если кастомные даты не заполнены
            start_date = today.replace(day=1)
            end_date = today
            prev_start_date = prev_end_date = None

        # Применяем остальные фильтры к базовому набору данных
        if cd.get("wallet"):
            queryset = queryset.filter(wallet=cd["wallet"])

        if cd["operation_type"]:
            queryset = queryset.filter(operation_type=cd["operation_type"])

        active_categories = cd.get("category", [])
        if active_categories:
            selected_categories_ids = [cat.id for cat in active_categories]
            queryset = queryset.filter(category__in=selected_categories_ids)

        # Разделяем на текущий кверисет и исторический (для трендов)
        past_queryset = queryset.filter(date__gte=prev_start_date, date__lte=prev_end_date) if prev_start_date else None
        queryset = queryset.filter(date__gte=start_date, date__lte=end_date).select_related("category",
                                                                                            "wallet").order_by("-date",
                                                                                                               "-id")

        # Агрегации
        stats = queryset.aggregate(
            total_sum=Sum('total'),
            total_count=Count('id'),
            avg_check=Avg('total')
        )

        metrics['total_sum'] = stats['total_sum'] or 0
        metrics['total_count'] = stats['total_count'] or 0
        metrics['avg_check'] = stats['avg_check'] or 0

        # Считаем тренды, если есть исторические данные
        if past_queryset:
            past_stats = past_queryset.aggregate(
                total_sum=Sum('total'),
                total_count=Count('id'),
                avg_check=Avg('total')
            )

            def calc_trend(current, past):
                if Atlantic_past := (past or 0):
                    return float(((current - Atlantic_past) / Atlantic_past) * 100)
                return None

            metrics['sum_trend'] = calc_trend(metrics['total_sum'], past_stats['total_sum'])
            metrics['count_trend'] = calc_trend(metrics['total_count'], past_stats['total_count'])
            metrics['avg_check_trend'] = calc_trend(metrics['avg_check'], past_stats['avg_check'])

            # Подсветка трендов (Расходы вверх — плохо/red, доходы вверх — хорошо/green)
            is_expense = cd.get("operation_type") == "expense"

            def get_trend_color(trend_val):
                if trend_val is None or trend_val == 0: return "text-muted"
                if is_expense:
                    return "text-danger" if trend_val > 0 else "text-success"
                return "text-success" if trend_val > 0 else "text-danger"

            metrics['count_trend_color'] = get_trend_color(metrics['count_trend'])
            metrics['avg_trend_color'] = get_trend_color(metrics['avg_check_trend'])
            metrics['sum_trend_color'] = "text-white opacity-85"

        # Данные для графиков
        aggregation_data = list(
            queryset
            .values("category__name")
            .annotate(total=Sum("total"))
            .order_by("-total")
        )

        if aggregation_data:
            metrics['top_category'] = aggregation_data[0]

        chart_data = [
            {"category": item["category__name"], "total": float(item["total"] or 0)}
            for item in aggregation_data
        ]

        # Данные для линейного графика хронологии
        timeline_data = list(
            queryset
            .order_by("date")
            .values("date")
            .annotate(total=Sum("total"))
        )

        chart_timeline = [
            {"date": item["date"].strftime("%d.%m"), "total": float(item["total"] or 0)}
            for item in timeline_data
        ]

    context = {
        'user': request.user,
        'user_transactions': queryset,
        'chart_data': json.dumps(chart_data),
        'chart_timeline': json.dumps(chart_timeline),  # Теперь хронология гарантированно передается в JSON
        'selected_category_ids': selected_categories_ids,
        'form': form,
        'metrics': metrics
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
        qs = (Wallet.accessible_for_user(self.request.user)
        .select_related('user')
        .prefetch_related('memberships__user')
        .order_by('-is_default', 'name'))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_qs = self.get_queryset()
        total = full_qs.aggregate(total=Sum('balance'))['total']
        context['total_sum'] = total or 0
        return context


class WalletShareInviteCreateView(LoginRequiredMixin, FormView):
    form_class = WalletShareInviteForm
    template_name = 'personal_finance/wallet_share.html'
    success_url = reverse_lazy('wallet_list')

    def dispatch(self, request, *args, **kwargs):
        self.wallet = Wallet.objects.filter(pk=kwargs["pk"], user=request.user, is_active=True).first()
        if not self.wallet:
            messages.error(request, "Нельзя отправить приглашение для этого счета.")
            return redirect("wallet_list")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["wallet"] = self.wallet
        return kwargs

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        User = get_user_model()
        target_user = User.objects.filter(username=username).first()

        already_member = WalletMember.objects.filter(
            wallet=self.wallet, user=target_user, status=WalletMember.MemberStatus.ACTIVE
        ).exists()
        if already_member:
            form.add_error("username", "Пользователь уже имеет доступ к этому счету.")
            return self.form_invalid(form)

        invite, created = WalletShareInvite.objects.get_or_create(
            wallet=self.wallet,
            from_user=self.request.user,
            to_user=target_user,
            status=WalletShareInvite.InviteStatus.PENDING,
            defaults={},
        )
        if not created:
            form.add_error("username", "Приглашение уже отправлено и ожидает ответа.")
            return self.form_invalid(form)

        NotificationsService.create_notification(
            actor=self.request.user,
            recipient=target_user,
            verb=f"приглашает вас разделить счет «{self.wallet.name}»",
            content_obj=invite,
        )
        messages.success(self.request, "Приглашение отправлено.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wallet"] = self.wallet
        return context


class WalletShareInviteRespondView(LoginRequiredMixin, View):
    def post(self, request, pk, action):
        invite = WalletShareInvite.objects.filter(
            pk=pk, to_user=request.user, status=WalletShareInvite.InviteStatus.PENDING
        ).first()
        if not invite:
            messages.error(request, "Приглашение не найдено или уже обработано.")
            return redirect("notifications:list")

        if action == "accept":
            WalletMember.objects.update_or_create(
                wallet=invite.wallet,
                user=request.user,
                defaults={
                    "status": WalletMember.MemberStatus.ACTIVE,
                    "role": WalletMember.RoleType.MEMBER,
                    "invited_by": invite.from_user,
                },
            )
            invite.status = WalletShareInvite.InviteStatus.ACCEPTED
            messages.success(request, f"Вы получили доступ к счету '{invite.wallet.name}'.")
        else:
            invite.status = WalletShareInvite.InviteStatus.DECLINED
            messages.info(request, "Приглашение отклонено.")

        invite.responded_at = timezone.now()
        invite.save(update_fields=["status", "responded_at", "updated_at"])
        NotificationsService.create_notification(
            actor=request.user,
            recipient=invite.from_user,
            verb=(
                f"принял(а) приглашение в счет '{invite.wallet.name}'"
                if action == "accept"
                else f"отклонил(а) приглашение в счет '{invite.wallet.name}'"
            ),
            content_obj=invite.wallet,
        )
        return redirect("wallet_list")


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
        user = self.request.user
        today = timezone.now().date()
        first_day_of_month = today.replace(day=1)

        # 1. Подзапрос на получение суммы лимита пользователя для конкретной категории
        limit_subquery = CategoryLimit.objects.filter(
            user=user,
            category=OuterRef('pk'),
            is_active=True
        ).values('amount')[:1]

        # 2. Подзапрос на сумму расходов по этой категории за ТЕКУЩИЙ месяц
        spent_subquery = PersonalTransaction.objects.filter(
            user=user,
            category=OuterRef('pk'),
            operation_type=OperationType.EXPENSE,
            date__gte=first_day_of_month,
            date__lte=today
        ).values('category').annotate(total=Sum('total')).values('total')[:1]

        # 3. Основной запрос с аннотациями и явным указанием типов для PostgreSQL
        decimal_field = models.DecimalField(max_digits=12, decimal_places=2)

        queryset = Category.objects.for_user(user=user).annotate(
            transaction_count=Count(
                'category_transactions',
                filter=~models.Q(category_transactions__operation_type='transfer') &
                       models.Q(category_transactions__user=user)
            ),
            # Явно передаем output_field, чтобы у СУБД не ехали типы
            limit_amount=Coalesce(
                Subquery(limit_subquery),
                Value(Decimal('0.00'), output_field=decimal_field)
            ),
            spent_this_month=Coalesce(
                Subquery(spent_subquery),
                Value(Decimal('0.00'), output_field=decimal_field)
            )
        ).order_by('-user_id', 'category_type', 'name')

        # 4. Вычисляем динамические метрики для CSS-анимаций и прогресс-баров в шаблоне
        categories_list = list(queryset)  # Оцениваем кверисет в список

        for cat in categories_list:
            if cat.limit_amount > 0:
                # Считаем процент утилизации лимита (но не более 100%, чтобы не ломать верстку бара)
                cat.limit_progress = min(100, int((cat.spent_this_month / cat.limit_amount) * 100))
                # Выставляем флаги критичности для изменения цвета (success/warning/danger)
                cat.is_limit_warning = 85 <= cat.limit_progress < 100
                cat.is_limit_danger = cat.limit_progress >= 100
            else:
                cat.limit_progress = 0
                cat.is_limit_warning = False
                cat.is_limit_danger = False

        return categories_list

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = CategoryForm(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        form = CategoryForm(data=request.POST, user=request.user)

        if form.is_valid():
            try:
                # 1. Создаем категорию через твой сервис
                category = FinanceService.create_category(
                    user=request.user,
                    name=form.cleaned_data['name'],
                    category_type=form.cleaned_data['category_type']
                )

                # 2. Перехватываем лимит и сохраняем его в БД
                limit_val = form.cleaned_data.get('limit_amount')
                if limit_val and form.cleaned_data['category_type'] == 'expense':
                    CategoryLimit.objects.update_or_create(
                        user=request.user,
                        category=category,
                        defaults={'amount': limit_val, 'is_active': True}
                    )

                messages.success(request, "Категория успешно добавлена!")
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
        # 1. ИСПРАВЛЕНО: используем for_user, чтобы юзер мог получить доступ
        # к системным категориям для настройки лимитов
        return Category.objects.for_user(user=self.request.user).filter(is_active=True)

    def form_valid(self, form):
        cd = form.cleaned_data
        category = self.object  # Текущая редактируемая категория

        try:
            # 2. Обновляем базовые поля категории через сервис
            # (внутри сервиса должна быть проверка: если category.user Is Null, то не менять name и type)
            FinanceService.update_category(
                category_obj=category,
                user=self.request.user,
                name=cd.get('name'),
                new_type=cd.get('category_type')
            )

            limit_val = cd.get('limit_amount')

            # Берем тип из объекта, так как для системных категорий поле на форме задизейблено
            if category.category_type == 'expense':
                if limit_val:
                    # Если лимит указан — создаем или обновляем его
                    CategoryLimit.objects.update_or_create(
                        user=self.request.user,
                        category=category,
                        defaults={'amount': limit_val, 'is_active': True}
                    )
                else:
                    # Если пользователь стер лимит (сделал поле пустым) — деактивируем текущий лимит
                    CategoryLimit.objects.filter(
                        user=self.request.user,
                        category=category
                    ).update(is_active=False)

            messages.success(self.request, "Категория успешно изменена!")
            return redirect(self.success_url)

        except ValidationError as e:
            # Вместо messages лучше вешать ошибку на форму, чтобы юзер видел её в контексте страницы
            form.add_error(None, e.message)
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