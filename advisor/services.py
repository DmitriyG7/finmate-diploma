from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F
from django.shortcuts import get_object_or_404
from django.utils import timezone

from advisor.models import SavingGoal, GoalContribution
from notifications.models import Notification
from notifications.services import NotificationsService
from personal_finance.models import PersonalTransaction, OperationType, Wallet, Category


@dataclass
class GoalAdvice:
    goal: SavingGoal
    saved_amount: Decimal
    remaining_amount: Decimal
    months_left: int
    required_per_month: Decimal
    avg_income_per_month: Decimal
    avg_expense_per_month: Decimal
    free_cashflow_per_month: Decimal
    gap_per_month: Decimal
    top_expense_categories: list
    recommendations: list[str]
    projected_target_date: date | None


@dataclass
class WhatIfScenario:
    expense_cut_percent: int
    income_raise_percent: int
    simulated_free_cashflow_per_month: Decimal
    simulated_gap_per_month: Decimal
    simulated_projected_target_date: date | None


@dataclass
class AllocationItem:
    goal: SavingGoal
    weight: int
    allocation_per_month: Decimal
    required_per_month: Decimal
    delta_to_required: Decimal


@dataclass
class AllocationPlan:
    free_cashflow_per_month: Decimal
    total_required_per_month: Decimal
    items: list[AllocationItem]


class AdvisorService:
    ANALYSIS_MONTHS = 3

    @staticmethod
    def build_goal_advice(*, user, goal: SavingGoal) -> GoalAdvice:
        saved = goal.saved_amount
        remaining = goal.remaining_amount
        months_left = AdvisorService._months_left(goal.target_date)

        required_per_month = Decimal("0.00")
        if remaining > 0:
            required_per_month = (remaining / Decimal(months_left)).quantize(Decimal("0.01"))

        avg_income = AdvisorService._avg_monthly_total(user=user, operation_type=OperationType.INCOME)
        avg_expense = AdvisorService._avg_monthly_total(user=user, operation_type=OperationType.EXPENSE)
        free_cashflow = (avg_income - avg_expense).quantize(Decimal("0.01"))
        gap = (required_per_month - free_cashflow).quantize(Decimal("0.01"))

        top_categories = AdvisorService._top_expense_categories(user=user)
        projected_target_date = AdvisorService._project_target_date(
            today=timezone.now().date(),
            remaining=remaining,
            free_cashflow=free_cashflow,
        )
        recommendations = AdvisorService._build_recommendations(
            goal=goal,
            remaining=remaining,
            months_left=months_left,
            required_per_month=required_per_month,
            free_cashflow=free_cashflow,
            gap=gap,
            top_categories=top_categories,
            projected_target_date=projected_target_date,
        )

        return GoalAdvice(
            goal=goal,
            saved_amount=saved,
            remaining_amount=remaining,
            months_left=months_left,
            required_per_month=required_per_month,
            avg_income_per_month=avg_income,
            avg_expense_per_month=avg_expense,
            free_cashflow_per_month=free_cashflow,
            gap_per_month=gap,
            top_expense_categories=top_categories,
            recommendations=recommendations,
            projected_target_date=projected_target_date,
        )

    @staticmethod
    def build_what_if(
        *,
        advice: GoalAdvice,
        expense_cut_percent: int = 0,
        income_raise_percent: int = 0,
    ) -> WhatIfScenario:
        expense_cut_percent = max(0, min(90, int(expense_cut_percent or 0)))
        income_raise_percent = max(0, min(300, int(income_raise_percent or 0)))

        expense_multiplier = Decimal("1.00") - (Decimal(expense_cut_percent) / Decimal("100"))
        income_multiplier = Decimal("1.00") + (Decimal(income_raise_percent) / Decimal("100"))

        simulated_expense = (advice.avg_expense_per_month * expense_multiplier).quantize(Decimal("0.01"))
        simulated_income = (advice.avg_income_per_month * income_multiplier).quantize(Decimal("0.01"))
        simulated_cashflow = (simulated_income - simulated_expense).quantize(Decimal("0.01"))
        simulated_gap = (advice.required_per_month - simulated_cashflow).quantize(Decimal("0.01"))

        simulated_date = AdvisorService._project_target_date(
            today=timezone.now().date(),
            remaining=advice.remaining_amount,
            free_cashflow=simulated_cashflow,
        )

        return WhatIfScenario(
            expense_cut_percent=expense_cut_percent,
            income_raise_percent=income_raise_percent,
            simulated_free_cashflow_per_month=simulated_cashflow,
            simulated_gap_per_month=simulated_gap,
            simulated_projected_target_date=simulated_date,
        )

    @staticmethod
    def notify_goal_risks(*, user) -> int:
        active_goals = SavingGoal.objects.filter(user=user, status=SavingGoal.StatusType.ACTIVE)
        created_count = 0
        today = timezone.now().date()

        for goal in active_goals:
            advice = AdvisorService.build_goal_advice(user=user, goal=goal)
            is_at_risk = (
                advice.remaining_amount > 0
                and advice.gap_per_month > 0
                and advice.months_left <= 3
            )
            if not is_at_risk:
                continue

            already_exists = Notification.objects.filter(
                recipient=user,
                actor=user,
                content_type__model="savinggoal",
                object_id=goal.id,
                created_at__date=today,
                verb__startswith="Риск по цели:",
            ).exists()
            if already_exists:
                continue

            formatted_gap = f"{advice.gap_per_month:,.0f}".replace(",", " ")


            clean_verb = f"Риск: дефицит {formatted_gap} ₽/мес по цели"

            NotificationsService.create_notification(
                actor=user,
                recipient=user,
                verb=clean_verb,
                content_obj=goal,
                allow_self=True,
            )
            created_count += 1

        return created_count

    @staticmethod
    def build_allocation_plan(*, user) -> AllocationPlan:
        goals = list(
            SavingGoal.objects.filter(user=user, status=SavingGoal.StatusType.ACTIVE).prefetch_related("contributions")
        )
        free_cashflow = AdvisorService._avg_monthly_total(user=user, operation_type=OperationType.INCOME) - AdvisorService._avg_monthly_total(
            user=user, operation_type=OperationType.EXPENSE
        )
        free_cashflow = free_cashflow.quantize(Decimal("0.01"))

        if not goals:
            return AllocationPlan(
                free_cashflow_per_month=free_cashflow,
                total_required_per_month=Decimal("0.00"),
                items=[],
            )

        priority_weights = {
            SavingGoal.PriorityType.HIGH: 5,
            SavingGoal.PriorityType.MEDIUM: 3,
            SavingGoal.PriorityType.LOW: 1,
        }

        weighted_items: list[tuple[SavingGoal, int, Decimal]] = []
        total_weight = 0
        total_required = Decimal("0.00")

        for goal in goals:
            advice = AdvisorService.build_goal_advice(user=user, goal=goal)
            required = advice.required_per_month
            weight = priority_weights.get(goal.priority, 1)
            if required > 0:
                weighted_items.append((goal, weight, required))
                total_weight += weight
                total_required += required

        if total_weight == 0:
            return AllocationPlan(
                free_cashflow_per_month=free_cashflow,
                total_required_per_month=Decimal("0.00"),
                items=[],
            )

        items: list[AllocationItem] = []
        distributable = free_cashflow if free_cashflow > 0 else Decimal("0.00")

        for goal, weight, required in weighted_items:
            share_ratio = Decimal(weight) / Decimal(total_weight)
            allocation = (distributable * share_ratio).quantize(Decimal("0.01"))
            delta = (allocation - required).quantize(Decimal("0.01"))
            items.append(
                AllocationItem(
                    goal=goal,
                    weight=weight,
                    allocation_per_month=allocation,
                    required_per_month=required,
                    delta_to_required=delta,
                )
            )

        items.sort(key=lambda item: (item.weight, item.required_per_month), reverse=True)
        return AllocationPlan(
            free_cashflow_per_month=free_cashflow,
            total_required_per_month=total_required.quantize(Decimal("0.01")),
            items=items,
        )

    @staticmethod
    def _months_left(target_date: date) -> int:
        today = timezone.now().date()
        if target_date <= today:
            return 1
        delta_days = (target_date - today).days
        months = (delta_days + 29) // 30
        return max(1, months)

    @staticmethod
    def _analysis_start() -> date:
        today = timezone.now().date()
        return today - timedelta(days=AdvisorService.ANALYSIS_MONTHS * 30)

    @staticmethod
    def _avg_monthly_total(*, user, operation_type: str) -> Decimal:
        total = (
            PersonalTransaction.objects.filter(
                user=user,
                operation_type=operation_type,
                date__gte=AdvisorService._analysis_start(),
            )
            .aggregate(total=Sum("total"))
            .get("total")
        ) or Decimal("0.00")
        return (total / Decimal(AdvisorService.ANALYSIS_MONTHS)).quantize(Decimal("0.01"))

    @staticmethod
    def _top_expense_categories(*, user, limit: int = 3) -> list:
        data = (
            PersonalTransaction.objects.filter(
                user=user,
                operation_type=OperationType.EXPENSE,
                date__gte=AdvisorService._analysis_start(),
            )
            .values("category__name")
            .annotate(total=Sum("total"))
            .order_by("-total")[:limit]
        )
        return list(data)

    @staticmethod
    def _build_recommendations(
        *,
        goal: SavingGoal,
        remaining: Decimal,
        months_left: int,
        required_per_month: Decimal,
        free_cashflow: Decimal,
        gap: Decimal,
        top_categories: list,
        projected_target_date: date | None,
    ) -> list[str]:
        recommendations: list[str] = []

        if remaining <= 0:
            recommendations.append("Цель уже достигнута. Можно зафиксировать как выполненную.")
            return recommendations

        recommendations.append(
            f"До цели осталось {remaining} ₽. Для срока {goal.target_date} нужно откладывать {required_per_month} ₽ в месяц."
        )

        if free_cashflow >= required_per_month:
            recommendations.append(
                f"Текущий свободный поток {free_cashflow} ₽/мес покрывает план. Цель выглядит реалистичной."
            )
        else:
            recommendations.append(
                f"Сейчас свободный поток {free_cashflow} ₽/мес. Не хватает примерно {gap} ₽/мес."
            )
            if top_categories:
                cats = ", ".join(
                    [f"{item['category__name']} ({item['total']} ₽)" for item in top_categories]
                )
                recommendations.append(
                    f"Проверь сокращение крупных расходов за последние 3 месяца: {cats}."
                )
        if projected_target_date:
            recommendations.append(
                f"При текущем темпе ориентировочная дата достижения: {projected_target_date.strftime('%d.%m.%Y')}."
            )
        else:
            recommendations.append(
                "При текущем темпе цель пока недостижима. Нужен положительный свободный поток."
            )

        if months_left <= 2 and remaining > 0:
            recommendations.append(
                "Срок близкий. Рассмотри перенос даты цели или увеличение разового пополнения."
            )

        return recommendations

    @staticmethod
    def _project_target_date(*, today: date, remaining: Decimal, free_cashflow: Decimal) -> date | None:
        if remaining <= 0:
            return today
        if free_cashflow <= 0:
            return None
        months_to_target = int((remaining / free_cashflow).to_integral_value(rounding=ROUND_CEILING))
        months_to_target = max(1, months_to_target)
        return today + timedelta(days=months_to_target * 30)

    @staticmethod
    def make_goal_contribution(*, user, goal, wallet_id, amount, date=None, comment=""):
        if date is None:
            date = timezone.now().date()

        with transaction.atomic():
            remaining = goal.remaining_amount
            if remaining <= 0:
                raise ValidationError(f"Цель «{goal.title}» уже полностью достигнута!")

            if amount > remaining:
                raise ValidationError(
                    f"Сумма превышает лимит цели. Чтобы закрыть цель, достаточно внести {remaining} ₽."
                )

            wallet = Wallet.objects.select_for_update().filter(id=wallet_id, user=user, is_active=True).first()
            if not wallet:
                raise ValidationError("Счет не найден или недоступен")

            if wallet.balance < amount:
                raise ValidationError(f"На счете «{wallet.name}» недостаточно средств. Баланс: {wallet.balance} ₽")

            wallet.balance = F("balance") - amount
            wallet.save()

            transaction_comment = comment or f"Пополнение цели: {goal.title}"
            try:
                category = Category.objects.get(name="Накопления", user__isnull=True, is_active=True)
            except Category.DoesNotExist:
                category = Category.objects.filter(is_active=True).first()

            PersonalTransaction.objects.create(
                user=user,
                wallet=wallet,
                operation_type=OperationType.EXPENSE,
                total=amount,
                description=transaction_comment,
                category=category
            )

            contribution = GoalContribution.objects.create(
                goal=goal,
                wallet=wallet,
                amount=amount,
                comment=comment,
                date=date
            )

            return contribution