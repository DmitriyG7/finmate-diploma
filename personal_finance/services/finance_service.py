from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

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
    def transfer(*, user, from_wallet_id, to_wallet_id, amount, idempotency_key=None):
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
    def update_transaction(*, transaction_obj, new_total=None, new_date=None, new_category=None, new_wallet=None, new_description=None):
        with transaction.atomic():
            if not PersonalTransaction.objects.select_for_update().filter(id=transaction_obj.id).exists():
                raise ValidationError("Транзакция не найдена или была удалена")

            wallet_ids = {transaction_obj.wallet.id}
            if new_wallet:
                wallet_ids.add(new_wallet.id)
            wallets_qs = Wallet.objects.select_for_update().filter(id__in=wallet_ids, user=transaction_obj.user, is_active=True)

            wallets_dict = {w.id: w for w in wallets_qs}

            old_wallet = wallets_dict.get(transaction_obj.wallet_id)
            target_wallet = wallets_dict.get(new_wallet.id) if new_wallet else old_wallet

            if not old_wallet or not target_wallet:
                raise ValidationError("Кошелек недоступен")

            if transaction_obj.operation_type == OperationType.EXPENSE:
                Wallet.objects.filter(id=old_wallet.id).update(balance=F("balance") + transaction_obj.total)
            else:
                Wallet.objects.filter(id=old_wallet.id).update(balance=F("balance") - transaction_obj.total)

            if new_date is not None:
                if new_date > timezone.now():
                    raise ValidationError("Неправильная дата. Транзакция не может быть будущим числом")
                transaction_obj.date=new_date

            if new_total is not None:
                transaction_obj.total = FinanceService._to_decimal(new_total)

            if new_category:
                category_qs = Category.objects.for_user(user=transaction_obj.user).filter(id=new_category.id)
                category = category_qs.first()
                if not category:
                    raise ValidationError("Категории не существует")

                if category.category_type != transaction_obj.category.category_type:
                    raise ValidationError("Неверный тип категории")
                transaction_obj.category = new_category

            if new_wallet:
                transaction_obj.wallet = new_wallet

            if new_description is not None:
                transaction_obj.description = new_description

            target_wallet.refresh_from_db()

            if transaction_obj.operation_type == OperationType.EXPENSE:
                if target_wallet.wallet_type == Wallet.WalletType.DEBET and target_wallet.balance < transaction_obj.total:
                    raise ValidationError(f"Недостаточно средств на счете '{target_wallet.name}'")

                Wallet.objects.filter(id=target_wallet.id).update(balance=F("balance") - transaction_obj.total)
            else:
                Wallet.objects.filter(id=target_wallet.id).update(balance=F("balance") + transaction_obj.total)

            transaction_obj.save()
            return transaction_obj

    @staticmethod
    def delete_transaction(*, transaction_obj):
        with transaction.atomic():
            transactions = PersonalTransaction.objects.select_for_update().filter(user=transaction_obj.user, id=transaction_obj.id)
            del_transaction = transactions.first()
            if del_transaction is None:
                raise ValidationError("Транзакция не найдена или уже удалена")

            wallets = Wallet.objects.select_for_update().filter(id=del_transaction.wallet.id, user=transaction_obj.user, is_active=True)
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
                    new_default_wallet.is_default = True
                    new_default_wallet.save(update_fields=['is_default'])

            timestamp = timezone.now().strftime("%Y%m%d_%H%M")
            new_name = f"{del_wallet.name} [архив {timestamp}]"

            wallets.update(name=new_name, is_default=False, is_active=False)
            del_wallet.refresh_from_db()
            return del_wallet