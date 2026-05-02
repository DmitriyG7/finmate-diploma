from django.utils import timezone
from django import forms
from django.core.exceptions import ValidationError
from .models import PersonalTransaction, Category, Wallet, WalletTransfer

from personal_finance.models import OperationType
from datetime import date, datetime
from decimal import Decimal

import re


PERIOD_CHOICES = [
    ("day", "Сегодня"),
    ("week", "Неделя"),
    ("month", "30 дней"),
    ("custom", "Выбрать даты"),
]

TYPE_CHOICES = [
    ("", "Все типы"),
    ("income", "Доход"),
    ("expense", "Расход")
]


class TransactionUserForm(forms.Form):
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='week', label="Период")
    operation_type = forms.ChoiceField(choices=TYPE_CHOICES, required=False, initial="", label="Тип транзакции")
    date_from = forms.DateField(label="Выберите начало", required=False,
                                input_formats=["%d.%m.%Y"],
                                widget=forms.DateInput(attrs={"placeholder": "дд.мм.гггг"}))
    date_to = forms.DateField(label="Выберите конец", required=False,
                              input_formats=["%d.%m.%Y"],
                              widget=forms.DateInput(attrs={"placeholder": "дд.мм.гггг"}))
    category = forms.ModelMultipleChoiceField(queryset=Category.objects.all(),
                                      widget=forms.CheckboxSelectMultiple, required=False,
                                      label="Выбранные категории")

    def clean(self):
        cd = super().clean()
        period = cd.get('period')
        date_from = cd.get('date_from')
        date_to = cd.get('date_to')

        if period == 'custom':
            if not date_from:
                self.add_error('date_from', "Укажите дату начала")
                # raise ValidationError("При выборе нужно указать начало и конец периода.")

            if not date_to:
                date_to = date.today()
                cd['date_to'] = date_to

            if date_from and date_to:
                if date_from > date_to:
                    raise ValidationError("Дата начала не может быть позже даты конца")
        return cd


class AddTransactionForm(forms.ModelForm):
    wallet = forms.ModelChoiceField(queryset=Wallet.objects.none(), required=True)
    date = forms.CharField(
        initial=timezone.now().date().strftime("%d.%m.%Y"),
        widget=forms.TextInput(attrs={'class': 'date-mask', 'placeholder': 'дд.мм.гггг'}),
        label="Дата"
    )
    operation_type = forms.ChoiceField(choices=[(OperationType.EXPENSE, "Расход"), (OperationType.INCOME, "Доход")],
                                       label="Тип транзакции")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=True,
                                      empty_label="Выберите категорию", label="Категория")
    total = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'money-mask', 'placeholder': '0.00'}),
                            label="Сумма")
    description = forms.CharField(widget=forms.Textarea(), required=False, label="Описание")

    class Meta:
        model = PersonalTransaction
        fields = ['category', 'description', 'date', 'total', 'operation_type', 'wallet']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            current_class = field.widget.attrs.get('class', '')
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.update({'class': f'{current_class} form-select'.strip()})
            elif not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': f'{current_class} form-control'.strip()})

        if user and user.is_authenticated:
            qs = Wallet.objects.filter(user=user, is_active=True)
            self.fields['wallet'].queryset = qs
            self.fields['category'].queryset = Category.objects.for_user(user=user)
            self.fields['wallet'].empty_label = None

            default_wallet = qs.filter(is_default=True).first()
            if default_wallet:
                self.fields['wallet'].initial = default_wallet
                # Это позволит JavaScript фильтровать категории
                category_field = self.fields['category']
                category_field.widget.attrs['data-types'] = 'true'  # Метка для JS

                # Переопределяем вывод категорий, добавляя data-type к каждому <option>
            choices = [("", "Выберите категорию")]
            for cat in category_field.queryset:
                choices.append((cat.id, cat.name))
            category_field.choices = choices

            # Создаем словарь {id: type} для JS
            self.category_types_map = {str(cat.id): cat.category_type for cat in category_field.queryset}

        else:
            self.fields['category'].queryset = Category.objects.base_categories()
            self.fields['wallet'].queryset = Wallet.objects.none()

    def clean_total(self):
        """Очистка суммы от маски: '1 200.50 ₽' -> Decimal('1200.50')"""
        total_raw = self.cleaned_data.get('total')
        # Удаляем всё, кроме цифр, точек и запятых
        clean_value = re.sub(r'[^\d.,]', '', str(total_raw)).replace(',', '.')
        try:
            value = Decimal(clean_value)
        except (ValueError, TypeError):
            raise ValidationError("Введите корректное число")

        if value <= 0:
            raise ValidationError("Сумма должна быть больше нуля")
        return value

    def clean_date(self):
        date_str = self.cleaned_data.get('date')
        if not date_str:
            return timezone.now().date()

        try:
            # Парсим именно наш формат: день.месяц.год
            dt = datetime.strptime(date_str, "%d.%m.%Y")

            # Проверка на "будущее", если это нужно по логике
            if dt.date() > timezone.now().date():
                raise ValidationError("Дата не может быть в будущем")

            return dt.date()
        except ValueError:
            raise ValidationError("Введите корректную дату в формате ДД.ММ.ГГГГ (например, 20.05.2026)")

    def clean(self):
        cd = super().clean()
        operation_type = cd.get("operation_type")
        category = cd.get("category")
        wallet = cd.get("wallet")
        total = cd.get("total")

        if category and operation_type and category.category_type != operation_type:
            self.add_error('category', "Тип категории не совпадает с типом операции.")

        return cd


class UpdateTransactionForm(AddTransactionForm):
    class Meta(AddTransactionForm.Meta):
        pass


class GraphicForm(TransactionUserForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['operation_type'].choices = OperationType.choices
        self.fields['operation_type'].initial = 'expense'


class CreateWalletForm(forms.ModelForm):
    balance = forms.CharField(label="Начальный баланс", widget=forms.TextInput(attrs={'class': 'money-mask'}))

    class Meta:
        model = Wallet
        fields = ['name', 'wallet_type', 'balance', 'currency', 'is_default']
        labels = {
            'name': 'Название',
            'wallet_type': 'Тип счета',
            'balance': 'Баланс',
            'currency': 'Валюта',
            'is_default': 'Сделать основным'
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Название счета'}),
            'balance': forms.TextInput(attrs={
                                            'class': 'form-control',
                                            'inputmode': 'decimal',
                                            'placeholder': '0.00',
                                        }),
        }

    def clean_balance(self):
        balance_raw = self.cleaned_data.get('balance')
        clean_value = re.sub(r'[^\d.,]', '', str(balance_raw)).replace(',', '.')
        return Decimal(clean_value)

    def clean(self):
        balance = self.cleaned_data.get('balance')

        if balance is None:
            return balance
        if balance < 0:
            raise ValidationError("Баланс не может быть отрицательным")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields['balance'].initial = None

        for field_name, field in self.fields.items():
            if field_name in ['wallet_type', 'currency']:
                # Класс form-select добавляет ту самую "галочку" справа
                field.widget.attrs.update({'class': 'form-select'})
            elif field_name == 'is_default':
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({'class': 'form-control'})


class UpdateWalletForm(CreateWalletForm):
    class Meta(CreateWalletForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['balance'].disabled = True
        self.fields['currency'].disabled = True
        self.fields['wallet_type'].disabled = True


class TransferForm(forms.ModelForm):
    amount = forms.CharField(label="Сумма перевода", widget=forms.TextInput(attrs={'class': 'money-mask'}))

    class Meta:
        model = WalletTransfer
        fields = ['from_wallet', 'to_wallet', 'amount', 'date']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated:
            self.fields['from_wallet'].queryset = Wallet.objects.filter(user=user, is_active=True)
            self.fields['to_wallet'].queryset = Wallet.objects.filter(user=user, is_active=True)

    def clean_amount(self):
        val = re.sub(r'[^\d.,]', '', str(self.cleaned_data['amount'])).replace(',', '.')
        return Decimal(val)

    def clean(self):
        cd = super().clean()
        from_wallet = cd.get("from_wallet")
        to_wallet = cd.get("to_wallet")
        amount = cd.get("amount")

        if from_wallet and to_wallet and from_wallet == to_wallet:
            self.add_error('to_wallet', "Нельзя перевести деньги на тот же самый счет.")

        if from_wallet and from_wallet.balance < amount:
            self.add_error('amount', f"Недостаточно средств. Доступно: {from_wallet.balance}")

        if from_wallet and to_wallet and from_wallet.currency != to_wallet.currency:
            self.add_error('to_wallet', "Конвертация между валютами пока не поддерживается.")

        return cd