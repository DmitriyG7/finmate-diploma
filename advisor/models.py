from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone


class SavingGoal(models.Model):
    class PriorityType(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"

    class StatusType(models.TextChoices):
        ACTIVE = "active", "Активная"
        ACHIEVED = "achieved", "Достигнута"
        PAUSED = "paused", "Пауза"
        ARCHIVED = "archived", "Архив"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saving_goals",
        verbose_name="Пользователь",
    )
    title = models.CharField(max_length=255, verbose_name="Название цели")
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
        verbose_name="Целевая сумма",
    )
    target_date = models.DateField(verbose_name="Срок достижения")
    start_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Уже накоплено на старте",
    )
    priority = models.CharField(
        max_length=10,
        choices=PriorityType.choices,
        default=PriorityType.MEDIUM,
        verbose_name="Приоритет",
    )
    status = models.CharField(
        max_length=10,
        choices=StatusType.choices,
        default=StatusType.ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )
    notes = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Цель накоплений"
        verbose_name_plural = "Цели накоплений"
        ordering = ["target_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user})"

    def get_absolute_url(self):
        return reverse("advisor:goal_detail", kwargs={"pk": self.pk})

    @property
    def contributed_amount(self) -> Decimal:
        total = self.contributions.aggregate(total=Sum("amount")).get("total")
        return total or Decimal("0.00")

    @property
    def saved_amount(self) -> Decimal:
        return (self.start_amount or Decimal("0.00")) + self.contributed_amount

    @property
    def remaining_amount(self) -> Decimal:
        remaining = self.target_amount - self.saved_amount
        return remaining if remaining > 0 else Decimal("0.00")

    @property
    def progress_percent(self) -> int:
        if self.target_amount <= 0:
            return 0
        ratio = (self.saved_amount / self.target_amount) * 100
        return int(min(100, max(0, ratio)))

    @property
    def is_overdue(self) -> bool:
        return self.status == self.StatusType.ACTIVE and timezone.now().date() > self.target_date


class GoalContribution(models.Model):
    goal = models.ForeignKey(
        SavingGoal,
        on_delete=models.CASCADE,
        related_name="contributions",
        verbose_name="Цель",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма пополнения",
    )
    date = models.DateField(default=timezone.now, verbose_name="Дата пополнения")
    wallet = models.ForeignKey("personal_finance.Wallet", on_delete=models.PROTECT,
                               related_name="goal_contributions", null=False, verbose_name="Счет списания")
    comment = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Пополнение цели"
        verbose_name_plural = "Пополнения целей"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.goal.title}: +{self.amount}"
