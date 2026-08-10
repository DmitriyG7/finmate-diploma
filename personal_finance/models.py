from django.utils import timezone

from django.conf import settings
from django.db import models
from users.models import Currency
from django.urls import reverse

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models import Q


class CategoryManager(models.Manager):
    def for_user(self, user, category_type=None):
        queryset = self.filter(Q(user=user) | Q(user__isnull=True), Q(is_active=True))

        if category_type:
            queryset = queryset.filter(category_type=category_type)
        return queryset

    def base_categories(self):
        return self.filter(user__isnull=True, is_active=True)


class OperationType(models.TextChoices):
    INCOME = 'income', 'Доход'
    EXPENSE = 'expense', 'Расход'
    TRANSFER = 'transfer', "Перевод"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Создатель")
    name = models.CharField(max_length=255, verbose_name="Имя категории")
    category_type = models.CharField(max_length=20, choices=[
            (OperationType.INCOME, 'Доход'),
            (OperationType.EXPENSE, 'Расход'),
        ], verbose_name="Тип категории")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активна")

    objects = CategoryManager()

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

        constraints = [
            models.UniqueConstraint(
                fields = ['user', 'name', 'category_type'],
                condition=models.Q(is_active=True),
                name = "unique_category_per_user"
            )
        ]

    def __str__(self):
        prefix = "[Системная]" if not self.user else f"[{self.user}]"
        return f"{prefix} {self.name} ({self.get_category_type_display()})"


class CategoryLimit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="limits")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="limits")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Ежемесячный лимит"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Лимит по категории"
        verbose_name_plural = "Лимиты по категориям"
        # У одного пользователя может быть только один лимит на конкретную категорию
        constraints = [
            models.UniqueConstraint(fields=['user', 'category'], name='unique_user_category_limit')
        ]

    def __str__(self):
        return f"Лимит {self.amount} ₽ на {self.category.name} ({self.user.username})"


class Wallet(TimeStampedModel):
    class WalletType(models.TextChoices):
        DEBET = "debet", "Дебетовый"
        CREDIT = "credit", "Кредитный"
        CRYPTO = "crypto", "Криптокошелек"
        SAVING = "saving", "Накопительный"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name="Пользователь", related_name="wallets")
    name = models.CharField(max_length=50, verbose_name="Название кошелька")
    wallet_type = models.CharField(max_length=15, choices=WalletType.choices, default=WalletType.DEBET,
                                   verbose_name="Тип счета")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                  verbose_name="Баланс")
    currency = models.CharField(max_length=6, choices=Currency.choices, default='RUB',
                                verbose_name="Тип валюты")
    is_default = models.BooleanField(default=True, verbose_name="Основной")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Кошелек"
        verbose_name_plural = "Кошельки"

        constraints = [
            models.UniqueConstraint(
                fields=['user', 'is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_wallet_per_user'
            ),
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='unique_wallet_name_per_user'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.balance} {self.currency})"

    @classmethod
    def accessible_for_user(cls, user):
        if not user or not user.is_authenticated:
            return cls.objects.none()
        return cls.objects.filter(
            Q(user=user) | Q(memberships__user=user, memberships__status=WalletMember.MemberStatus.ACTIVE),
            is_active=True,
        ).distinct()

    def is_owner(self, user):
        return self.user_id == getattr(user, "id", None)

    def is_shared(self):
        return self.memberships.filter(status=WalletMember.MemberStatus.ACTIVE).exists()


class PersonalTransaction(TimeStampedModel):
    total = models.DecimalField(max_digits=12, decimal_places=2, null=False,
                                validators=[MinValueValidator(Decimal('0.01'))], verbose_name="Сумма")
    date = models.DateField(db_index=True, default=timezone.now, verbose_name="Дата")
    description = models.TextField(blank=True, verbose_name="Описание")
    category = models.ForeignKey('Category', on_delete=models.PROTECT, verbose_name="Категория",
                                  related_name='category_transactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь",
                             db_index=True, related_name='transactions')
    operation_type = models.CharField(max_length=20, default=OperationType.EXPENSE,
                                      choices=OperationType.choices)
    wallet = models.ForeignKey('Wallet', on_delete=models.PROTECT, null=False, blank=False,
                               verbose_name="Счет", related_name="transactions")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="performed_transactions",
        verbose_name="Кем выполнено",
    )

    def __str__(self):
        category_name = self.category.name if self.category else "Без категории"
        return f"{self.date} | {self.get_operation_type_display()}: {self.total} ({category_name})"


class WalletTransfer(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь")
    from_wallet = models.ForeignKey('Wallet', on_delete=models.PROTECT, related_name='transfers_from',
                                    verbose_name="Откуда")
    to_wallet = models.ForeignKey('Wallet', on_delete=models.PROTECT, related_name="transfers_to",
                                  verbose_name="Куда")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=False,
                                 validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Сумма перевода")
    date = models.DateTimeField(default=timezone.now, verbose_name="Дата перевода")
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        verbose_name = "Перевод между счетами"
        verbose_name_plural = "Переводы между счетами"

        constraints = [
            models.UniqueConstraint(
            fields=["user", "idempotency_key"],
            name="uniq_wallet_transfer_user_idempotency_key",
        )
        ]

    def __str__(self):
        return f"Перевод {self.amount} из {self.from_wallet.name} в {self.to_wallet.name}"


class WalletMember(TimeStampedModel):
    class RoleType(models.TextChoices):
        OWNER = "owner", "Владелец"
        MEMBER = "member", "Участник"

    class MemberStatus(models.TextChoices):
        ACTIVE = "active", "Активен"
        REVOKED = "revoked", "Отключен"

    wallet = models.ForeignKey("Wallet", on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet_memberships")
    role = models.CharField(max_length=10, choices=RoleType.choices, default=RoleType.MEMBER)
    status = models.CharField(max_length=10, choices=MemberStatus.choices, default=MemberStatus.ACTIVE, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_member_invites_created",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wallet", "user"], name="uniq_wallet_member_wallet_user"),
        ]


class WalletShareInvite(TimeStampedModel):
    class InviteStatus(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        ACCEPTED = "accepted", "Принято"
        DECLINED = "declined", "Отклонено"
        CANCELLED = "cancelled", "Отменено"

    wallet = models.ForeignKey("Wallet", on_delete=models.CASCADE, related_name="share_invites")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet_share_sent")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet_share_received")
    status = models.CharField(max_length=10, choices=InviteStatus.choices, default=InviteStatus.PENDING, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "to_user"],
                condition=models.Q(status="pending"),
                name="uniq_pending_wallet_invite",
            )
        ]

    @property
    def title(self):
        return f"Приглашение в счет «{self.wallet.name}»"

    def get_absolute_url(self):
        return reverse("wallet_list")