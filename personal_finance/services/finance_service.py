from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.db import models

from finmate import settings
from personal_finance.models import Wallet, WalletTransfer, PersonalTransaction, Category
from personal_finance.models import OperationType
from django.contrib.auth import get_user_model


class FinanceService:
    @staticmethod
    def _to_decimal(amount) -> Decimal:
        try:
            value = Decimal(str(amount))
        except Exception:
            raise ValidationError("Некорректная сумма")
        if value <= 0:
            raise ValidationError("Сумма должна быть больше нуля")
        return value

    @staticmethod
    def transfer(*, user, from_wallet_id, to_wallet_id, amount, date=None, idempotency_key=None):
        amount = FinanceService._to_decimal(amount)

        with transaction.atomic():
            if from_wallet_id == to_wallet_id:
                raise ValueError("Нельзя перевести на тот же счет")

            if idempotency_key:
                existing = WalletTransfer.objects.filter(user=user,
                                                         idempotency_key=idempotency_key
                                                         ).first()
                if existing:
                    return existing

            wallets = list(
                Wallet.objects
                .select_for_update()
                .filter(id__in=[from_wallet_id, to_wallet_id], user=user, is_active=True)
            )

            if len(wallets) != 2:
                raise ValidationError("Один из счетов не найден или недоступен")

            if date is None:
                date = timezone.now()

            wallet_map = {w.id: w for w in wallets}
            from_wallet = wallet_map[from_wallet_id]
            to_wallet = wallet_map[to_wallet_id]

            if from_wallet.balance < amount:
                raise ValidationError("Недостаточно средств")

            if from_wallet.currency != to_wallet.currency:
                raise ValidationError(
                    f"Невозможно перевести из {from_wallet.currency} в {to_wallet.currency} без конвертации."
                )

            Wallet.objects.filter(id=from_wallet_id).update(balance=F("balance") - amount)
            Wallet.objects.filter(id=to_wallet_id).update(balance=F("balance") + amount)

            transfer = WalletTransfer.objects.create(
                user=user,
                from_wallet=from_wallet,
                to_wallet=to_wallet,
                amount=amount,
                idempotency_key=idempotency_key
            )

            category = Category.objects.filter(name="Перевод", user__isnull=True).first()
            if not category:
                raise ValidationError("Ошибка перевода. Обратитесь в поддержку")

            PersonalTransaction.objects.create(
                user=user,
                wallet=from_wallet,
                total=amount,
                date=date,
                category=category,
                operation_type=OperationType.TRANSFER,
                description=f"Перевод на счет {to_wallet.name}"
            )

            PersonalTransaction.objects.create(
                user=user,
                wallet=to_wallet,
                total=amount,
                date=date,
                category=category,
                operation_type=OperationType.TRANSFER,
                description=f"Перевод со счета {from_wallet.name}"
            )
            return transfer

    @staticmethod
    def create_transaction(*, user, wallet_id, amount, operation_type, category, description="", date=None):
        amount = FinanceService._to_decimal(amount)

        if operation_type not in {
            OperationType.EXPENSE,
            OperationType.INCOME
        }:
            raise ValidationError("Некорректный тип операции")

        if date is None:
            date = timezone.now().date()

        with transaction.atomic():
            wallet = (Wallet.objects
            .select_for_update()
            .filter(id=wallet_id, user=user, is_active=True).first())

            if not wallet:
                raise ValidationError("Кошелек не найден или недоступен")

            if operation_type == OperationType.EXPENSE:
                if wallet.balance < amount:
                    raise ValidationError("Недостаточно средств")
                Wallet.objects.filter(id=wallet.id).update(balance=F("balance") - amount)
            else:
                Wallet.objects.filter(id=wallet.id).update(balance=F("balance") + amount)

            if category is None:
                raise ValidationError("Категория обязательна")

            transaction_obj = PersonalTransaction.objects.create(
                user=user,
                wallet=wallet,
                total=amount,
                operation_type=operation_type,
                category=category,
                description=description,
                date=date
            )
            return transaction_obj

    @staticmethod
    def update_transaction(
            *,
            transaction_obj,
            new_total=None,
            new_date=None,
            new_category=None,
            new_wallet=None,
            new_description=None
    ):
        with transaction.atomic():

            # Лочим транзакцию и берём актуальные данные
            transaction_obj = PersonalTransaction.objects.select_for_update().get(
                id=transaction_obj.id,
                user=transaction_obj.user
            )

            old_total = transaction_obj.total
            old_wallet_id = transaction_obj.wallet_id

            # Если кошелёк не передан — работаем со старым
            target_wallet_id = new_wallet.id if new_wallet else old_wallet_id

            # Лочим задействованные кошельки
            wallet_ids = {old_wallet_id, target_wallet_id}
            wallets = Wallet.objects.select_for_update().filter(
                id__in=wallet_ids,
                user=transaction_obj.user,
                is_active=True
            )

            wallets_dict = {w.id: w for w in wallets}

            old_wallet = wallets_dict.get(old_wallet_id)
            target_wallet = wallets_dict.get(target_wallet_id)

            if not old_wallet or not target_wallet:
                raise ValidationError("Кошелек недоступен")

            # Проверяем нужно ли трогать баланс
            balance_changed = (
                    new_total is not None or
                    new_wallet is not None
            )

            if balance_changed:
                # 1. ОТКАТ старой транзакции
                if transaction_obj.operation_type == OperationType.EXPENSE:
                    Wallet.objects.filter(id=old_wallet.id).update(
                        balance=F("balance") + old_total
                    )
                else:
                    Wallet.objects.filter(id=old_wallet.id).update(
                        balance=F("balance") - old_total
                    )

            if new_date is not None:
                if new_date > timezone.now().date():
                    raise ValidationError("Дата не может быть в будущем")
                transaction_obj.date = new_date

            if new_total is not None:
                transaction_obj.total = FinanceService._to_decimal(new_total)

            if new_category:
                category = Category.objects.filter(
                    models.Q(user=transaction_obj.user) | models.Q(user__isnull=True),
                    id=new_category.id
                ).first()

                if not category:
                    raise ValidationError("Категория не существует")

                if category.category_type != transaction_obj.category.category_type:
                    raise ValidationError("Неверный тип категории")

                transaction_obj.category = category

            if new_wallet:
                transaction_obj.wallet = new_wallet

            if new_description is not None:
                transaction_obj.description = new_description

            # ПРИМЕНЕНИЕ новой транзакции
            if balance_changed:
                new_total_value = transaction_obj.total

                if transaction_obj.operation_type == OperationType.EXPENSE:

                    # Проверка баланса (только для дебетового)
                    if (
                            target_wallet.wallet_type == Wallet.WalletType.DEBET and
                            target_wallet.balance < new_total_value
                    ):
                        raise ValidationError(
                            f"Недостаточно средств на счете '{target_wallet.name}'"
                        )

                    Wallet.objects.filter(id=target_wallet.id).update(
                        balance=F("balance") - new_total_value
                    )

                else:
                    Wallet.objects.filter(id=target_wallet.id).update(
                        balance=F("balance") + new_total_value
                    )

            # 💾 Сохраняем транзакцию
            transaction_obj.save()

            return transaction_obj

    @staticmethod
    def delete_transaction(*, transaction_obj):
        with transaction.atomic():
            transactions = PersonalTransaction.objects.select_for_update().filter(user=transaction_obj.user, id=transaction_obj.id)
            del_transaction = transactions.first()
            if del_transaction is None:
                raise ValidationError("Транзакция не найдена или уже удалена")

            wallets = Wallet.objects.select_for_update().filter(id=del_transaction.wallet.id, user=transaction_obj.user)
            blocked_wallet = wallets.first()
            if not blocked_wallet:
                raise ValidationError("Счет не найден или недоступен")

            money = del_transaction.total
            if del_transaction.operation_type == OperationType.EXPENSE:
                wallets.update(balance=F("balance") + money)

            elif del_transaction.operation_type == OperationType.INCOME:
                if blocked_wallet.wallet_type == Wallet.WalletType.DEBET and blocked_wallet.balance < money:
                    raise ValidationError("Недостаточно средств для отмены дохода")
                wallets.update(balance=F("balance") - money)

            del_transaction.delete()


    @staticmethod
    def create_wallet(*, user, name, wallet_type, balance=0, currency, is_default=False):
        with transaction.atomic():
            User = get_user_model()
            locked_user = User.objects.select_for_update().get(id=user.id)

            if Wallet.objects.filter(user=locked_user, name=name, is_active=True).exists():
                raise ValidationError(f"Счет с именем «{name}» уже существует")

            if locked_user.wallets.count() >= settings.MAX_WALLETS_PER_USER:
                raise ValidationError(f"Вы достигли лимита в {settings.MAX_WALLETS_PER_USER} счетов")

            if balance < 0:
                raise ValidationError("Баланс должен быть положительным")

            if is_default:
                Wallet.objects.filter(user=user, is_default=True).update(is_default=False)

            wallet = Wallet.objects.create(
                user=user,
                name=name,
                wallet_type=wallet_type,
                balance=balance,
                currency=currency,
                is_default=is_default
            )
            return wallet

    @staticmethod
    def update_wallet(*, wallet, name, is_default):
        with transaction.atomic():
            wallets = (Wallet.objects.select_for_update().filter(id=wallet.id, user=wallet.user, is_active=True))
            update_wallet = wallets.first()

            if not update_wallet:
                raise ValidationError("Счет не существует или недоступен")

            if update_wallet.name != name:
                if Wallet.objects.filter(user=wallet.user, name=name, is_active=True).exists():
                    raise ValidationError(f"У вас уже есть счет с названием '{name}'")

            if is_default:
                Wallet.objects.filter(user=wallet.user, is_default=True, is_active=True).exclude(id=wallet.id).update(is_default=False)
            else:
                other_wallets = Wallet.objects.filter(user=wallet.user, is_default=True, is_active=True).exclude(id=wallet.id).exists()
                if update_wallet.is_default and not other_wallets:
                    raise ValidationError("Нельзя убрать статус основного счета, если нет альтернативы.")

            wallets.update(name=name, is_default=is_default)
            update_wallet.refresh_from_db()
            return update_wallet

    @staticmethod
    def delete_wallet(*, wallet):
        with transaction.atomic():
            wallets = (Wallet.objects.select_for_update().filter(id=wallet.id, user=wallet.user, is_active=True))
            del_wallet = wallets.first()

            if not del_wallet:
                raise ValidationError("Счет не найден или уже удален")

            if del_wallet.is_default:
                new_default_wallet = Wallet.objects.filter(user=del_wallet.user, is_active=True, is_default=False).exclude(id=del_wallet.id).first()
                if new_default_wallet:
                    Wallet.objects.filter(user=del_wallet.user, is_default=True).update(is_default=False)
                    new_default_wallet.is_default = True
                    new_default_wallet.save(update_fields=['is_default'])

            timestamp = timezone.now().strftime("%Y%m%d_%H%M")
            new_name = f"{del_wallet.name} [архив {timestamp}]"

            wallets.update(name=new_name, is_default=False, is_active=False)
            del_wallet.refresh_from_db()
            return del_wallet


    @staticmethod
    def create_category(*, user, name, category_type):
        with transaction.atomic():
            if Category.objects.for_user(user=user).filter(name=name, category_type=category_type).exists():
                raise ValidationError(f"Категория '{name}' уже существует.")

            return Category.objects.create(
                user=user,
                name=name,
                category_type=category_type,
                is_active=True
            )

    @staticmethod
    def update_category(*, category_obj, user, name=None, new_type=None):
        with transaction.atomic():
            category = (Category.objects.select_for_update()
                        .filter(id=category_obj.id, user=user, is_active=True).first())

            if not category:
                raise ValidationError("Категория не найдена или недоступна.")

            if category.user is None:
                raise ValidationError("Нельзя редактировать системные категории.")

            target_name = name if name is not None else category.name
            target_type = new_type if new_type is not None else category.category_type

            duplicate_exists = Category.objects.filter(
                user=user,
                name=target_name,
                category_type=target_type,
                is_active=True
            ).exclude(id=category.id).exists()

            if duplicate_exists:
                raise ValidationError(f"Категория '{target_name}' с таким типом уже существует.")

            category.name = target_name
            category.category_type = target_type

            # .save() вызовет сигналы и обновит auto_now поля, если они есть
            category.save()

            return category

    @staticmethod
    def delete_category(*, category_obj, user):
        with transaction.atomic():
            category = Category.objects.select_for_update().filter(id=category_obj.id, user=user, is_active=True).first()

            if not category:
                raise ValidationError("Категория не найдена или уже удалена")

            if category.user is None:
                raise ValidationError("Нельзя удалить системную категорию")

            category.is_active=False
            category.save()
            return category