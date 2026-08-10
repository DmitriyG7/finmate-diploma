from django.utils import timezone
from django import forms
from django.core.exceptions import ValidationError
from .models import PersonalTransaction, Category, CategoryLimit, Wallet, WalletTransfer
from django.db import models

from personal_finance.models import OperationType
from datetime import date, datetime
from decimal import Decimal

import re

# --- MIXIN ---

class FinanceFormMixin:
    """Миксин для автоматизации стилизации и очистки масок"""

    def apply_finance_styles(self):
        """Автоматически добавляет классы Bootstrap и маски"""
        for field_name, field in self.fields.items():
            # Базовые классы
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css_class = 'form-select'
            elif isinstance(field.widget, forms.CheckboxInput):
                css_class = 'form-check-input'
            else:
                css_class = 'form-control'

            # Добавляем маски на основе имени поля или типа
            if any(word in field_name for word in ['total', 'amount', 'balance']):
                css_class += ' money-mask'
            if field_name in ['date', 'date_from', 'date_to'] or isinstance(field, forms.DateField):
                css_class += ' date-mask'

            field.widget.attrs.update({'class': css_class})

    def parse_money(self, field_name):
        """Метод для очистки денежных полей от маски"""
        raw_val = self.cleaned_data.get(field_name)
        if raw_val is None or raw_val == '': return Decimal('0.00')
        clean_val = re.sub(r'[^\d.,]', '', str(raw_val)).replace(',', '.')
        try:
            return Decimal(clean_val)
        except (ValueError, TypeError):
            raise ValidationError("Введите корректное число")

    def parse_date(self, field_name):
        """Метод для парсинга русской даты"""
        date_str = self.cleaned_data.get(field_name)
        if not date_str: return timezone.now().date()
        try:
            dt = datetime.strptime(str(date_str), "%d.%m.%Y")
            return dt.date()
        except ValueError:
            raise ValidationError("Введите дату в формате ДД.ММ.ГГГГ")

# --- FORMS ---

PERIOD_CHOICES = [
    ("today", "Сегодня"),
    ("week", "Неделя"),
    ("month", "Текущий месяц"),
    ("last_month", "Прошлый месяц"),
    ("custom", "Выбрать даты"),
]

TYPE_CHOICES = [
    ("", "Все типы"),
    ("income", "Доход"),
    ("expense", "Расход"),
    ("transfer", "Перевод"),
]


class TransactionUserForm(FinanceFormMixin, forms.Form):
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='month', label="Период")
    operation_type = forms.ChoiceField(choices=TYPE_CHOICES, required=False, initial="", label="Тип транзакции")
    date_from = forms.DateField(label="Выберите начало", required=False, input_formats=["%d.%m.%Y"])
    date_to = forms.DateField(label="Выберите конец", required=False, input_formats=["%d.%m.%Y"])
    category = forms.ModelMultipleChoiceField(queryset=Category.objects.all(),
                                      widget=forms.CheckboxSelectMultiple, required=False,
                                      label="Выбранные категории")
    wallet = forms.ModelChoiceField(queryset=Wallet.objects.none(), required=False,
                                    empty_label="Все счета", label="Счет")

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.apply_finance_styles()

        if user and user.is_authenticated:
            self.fields['wallet'].queryset = Wallet.accessible_for_user(user=user)
            self.fields['category'].queryset = Category.objects.for_user(user=user)

    def clean(self):
        cd = super().clean()
        period = cd.get('period')
        date_from = cd.get('date_from')
        date_to = cd.get('date_to')

        if period == 'custom':
            if not date_from:
                self.add_error('date_from', "Укажите дату начала")
            if not date_to:
                cd['date_to'] = timezone.now().date()
            if date_from and cd.get('date_to') and date_from > cd.get('date_to'):
                self.add_error('date_from', "Дата начала не может быть позже даты конца")
        return cd


class AddTransactionForm(FinanceFormMixin, forms.ModelForm):
    wallet = forms.ModelChoiceField(queryset=Wallet.objects.none(), required=True)
    date = forms.CharField(initial=lambda: timezone.now().date().strftime("%d.%m.%Y"), label="Дата")
    operation_type = forms.ChoiceField(choices=[(OperationType.EXPENSE, "Расход"), (OperationType.INCOME, "Доход")],
                                       label="Тип транзакции")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=True,
                                      empty_label="Выберите категорию", label="Категория")
    total = forms.CharField(required=True, label="Сумма")
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label="Описание")

    class Meta:
        model = PersonalTransaction
        fields = ['category', 'description', 'date', 'total', 'operation_type', 'wallet']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.apply_finance_styles()

        if self.instance and self.instance.pk and self.instance.date:
            self.initial['date'] = self.instance.date.strftime('%d.%m.%Y')

        if user and user.is_authenticated:
            active_cats = Category.objects.for_user(user=user)
            qs = Wallet.accessible_for_user(user=user)
            self.fields['wallet'].queryset = qs
            self.fields['category'].queryset = Category.objects.for_user(user=user)
            self.fields['wallet'].empty_label = None

            if self.instance and self.instance.category_id:
                self.fields['category'].queryset = Category.objects.filter(
                    models.Q(id__in=active_cats.values_list('id', flat=True)) |
                    models.Q(id=self.instance.category_id)
                ).order_by("category_type", "name")
            else:
                self.fields['category'].queryset = active_cats

            default_wallet = qs.filter(is_default=True).first()
            if default_wallet:
                self.fields['wallet'].initial = default_wallet

            category_field = self.fields['category']
            choices = [("", "Выберите категорию")]
            for cat in category_field.queryset:
                choices.append((cat.id, cat.name))
            category_field.choices = choices
            self.category_types_map = {str(cat.id): cat.category_type for cat in category_field.queryset}
        else:
            self.fields['category'].queryset = Category.objects.base_categories()
            self.fields['wallet'].queryset = Wallet.objects.none()

    def clean_total(self):
        val = self.parse_money('total')
        if val <= 0: raise ValidationError("Сумма должна быть больше нуля")
        return val

    def clean_date(self):
        dt = self.parse_date('date')
        if dt > timezone.now().date():
            raise ValidationError("Дата не может быть в будущем")
        return dt

    def clean(self):
        cd = super().clean()
        operation_type = cd.get("operation_type")
        category = cd.get("category")
        if category and operation_type and category.category_type != operation_type:
            self.add_error('category', "Тип категории не совпадает с типом операции.")

        if self.instance and self.instance.pk:
            # Проверяем, была ли у этой транзакции категория "Накопления" до изменения
            # (или проверяем прилетевшую категорию)
            if self.instance.category and self.instance.category.name == "Накопления":
                raise ValidationError(
                    "Эта транзакция создана автоматически финансовым советником. "
                    "Её нельзя редактировать напрямую. Изменения вносятся через управление целями."
                )

        return cd


class UpdateTransactionForm(AddTransactionForm):
    class Meta(AddTransactionForm.Meta):
        pass


class GraphicForm(TransactionUserForm):
    operation_type = forms.ChoiceField(choices=((OperationType.EXPENSE.value, "Расход"), (OperationType.INCOME.value, "Доход")
                                                    ),required=False, initial="", label="Тип транзакции")


class CreateWalletForm(FinanceFormMixin, forms.ModelForm):
    balance = forms.CharField(label="Начальный баланс")

    class Meta:
        model = Wallet
        fields = ['name', 'wallet_type', 'balance', 'currency', 'is_default']
        labels = {
            'name': 'Название',
            'wallet_type': 'Тип счета',
            'currency': 'Валюта',
            'is_default': 'Сделать основным'
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields['balance'].initial = None
        self.apply_finance_styles()

    def clean_balance(self):
        val = self.parse_money('balance')
        if val < 0: raise ValidationError("Баланс не может быть отрицательным")
        return val


class UpdateWalletForm(CreateWalletForm):
    class Meta(CreateWalletForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['balance'].disabled = True
        self.fields['currency'].disabled = True
        self.fields['wallet_type'].disabled = True
        self.apply_finance_styles()


class TransferForm(FinanceFormMixin, forms.ModelForm):
    amount = forms.CharField(label="Сумма перевода")
    date = forms.CharField(initial=lambda: timezone.now().date().strftime("%d.%m.%Y"), label="Дата")

    class Meta:
        model = WalletTransfer
        fields = ['from_wallet', 'to_wallet', 'amount', 'date']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.apply_finance_styles()

        if user and user.is_authenticated:
            qs = Wallet.accessible_for_user(user=user)
            self.fields['from_wallet'].queryset = qs
            self.fields['to_wallet'].queryset = qs

            default_wallet = qs.filter(is_default=True).first()
            if default_wallet:
                self.fields['from_wallet'].initial = default_wallet

    def clean_amount(self):
        return self.parse_money('amount')

    def clean_date(self):
        return self.parse_date('date')

    def clean(self):
        cd = super().clean()
        from_wallet = cd.get("from_wallet")
        to_wallet = cd.get("to_wallet")
        amount = cd.get("amount")

        if from_wallet and to_wallet and from_wallet == to_wallet:
            self.add_error('to_wallet', "Нельзя перевести деньги на тот же самый счет.")
        if from_wallet and amount and from_wallet.balance < amount:
            self.add_error('amount', f"Недостаточно средств. Доступно: {from_wallet.balance}")
        if from_wallet and to_wallet and from_wallet.currency != to_wallet.currency:
            self.add_error('to_wallet', "Конвертация между валютами пока не поддерживается.")
        return cd


class CategoryForm(FinanceFormMixin, forms.ModelForm):
    # Добавляем поле лимита прямо в форму
    limit_amount = forms.DecimalField(
        required=False,
        min_value=Decimal('0.01'),
        max_digits=12,
        decimal_places=2,
        label="Месячный лимит трат",
        widget=forms.TextInput(attrs={'placeholder': 'Например: 15000'})
    )

    class Meta:
        model = Category
        fields = ['name', 'category_type']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.apply_finance_styles()

        # Меняем дефолтный пустой выбор
        current_choices = self.fields['category_type'].choices
        new_choices = list(current_choices)
        new_choices[0] = ("", "Выберите тип")
        self.fields['category_type'].choices = new_choices

        # Если мы РЕДАКТИРУЕМ существующую категорию
        if self.instance and self.instance.pk:
            # 1. Подтягиваем текущий лимит в поле формы
            existing_limit = CategoryLimit.objects.filter(
                user=self.user,
                category=self.instance,
                is_active=True
            ).first()
            if existing_limit:
                self.fields['limit_amount'].initial = existing_limit.amount

            # 2. ЗАЩИТА: Если категория СИСТЕМНАЯ, запрещаем менять имя и тип, но лимит менять МОЖНО
            if self.instance.user is None:
                self.fields['name'].disabled = True
                self.fields['category_type'].disabled = True
            else:
                # Для обычных категорий при редактировании просто блочим тип
                self.fields['category_type'].disabled = True

    def clean(self):
        cd = super().clean()
        name = cd.get("name")
        category_type = cd.get("category_type")

        # Если поле задизейблено, Django не возвращает его в cleaned_data, берем из инстанса
        if not category_type and self.instance and self.instance.pk:
            category_type = self.instance.category_type
        if not name and self.instance and self.instance.pk:
            name = self.instance.name

        # Если тип категории — доход, лимит не имеет смысла
        if category_type == 'income':
            cd['limit_amount'] = None

        # Проверка уникальности: только если категория НЕ системная
        is_system = self.instance and self.instance.pk and self.instance.user is None
        if name is not None and category_type is not None and not is_system:
            queryset = Category.objects.filter(
                user=self.user,
                name=name,
                category_type=category_type,
                is_active=True
            )
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(id=self.instance.pk)

            if queryset.exists():
                self.add_error('name', "Категория с таким именем и типом уже существует")

        return cd


class WalletShareInviteForm(forms.Form):
    username = forms.CharField(max_length=150, label="Логин пользователя")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        self.wallet = kwargs.pop("wallet")
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-control", "placeholder": "Введите логин"})

    def clean_username(self):
        from django.contrib.auth import get_user_model

        username = self.cleaned_data["username"].strip()
        User = get_user_model()
        target = User.objects.filter(username=username).first()
        if not target:
            raise ValidationError("Пользователь с таким логином не найден.")
        if target.id == self.user.id:
            raise ValidationError("Нельзя отправить приглашение самому себе.")
        return username