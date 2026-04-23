from django.utils import timezone
from django import forms
from django.core.exceptions import ValidationError
from .models import PersonalTransaction, Category

from datetime import date


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
    date = forms.DateField(initial=timezone.now().date(), input_formats=['%d.%m.%Y'],
                           widget=forms.DateInput(attrs={"placeholder": "дд.мм.гггг"}, format='%d.%m.%Y'),
                           label="Выберите дату")
    operation_type = forms.ChoiceField(choices=PersonalTransaction.OperationType.choices, label="Тип транзакции")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=True,
                                      empty_label="Выберите категорию", label="Категория")
    total = forms.DecimalField(required=True, widget=forms.NumberInput(), label="Сумма")
    description = forms.CharField(widget=forms.Textarea(), required=False, label="Описание")

    class Meta:
        model = PersonalTransaction
        fields = ['category', 'description', 'date', 'total', 'operation_type']


class UpdateTransactionForm(forms.ModelForm):
    class Meta:
        model = PersonalTransaction
        fields = ['category', 'description', 'date', 'operation_type', 'total']

class GraphicForm(TransactionUserForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['operation_type'].choices = PersonalTransaction.OperationType.choices
        self.fields['operation_type'].initial = 'expense'

