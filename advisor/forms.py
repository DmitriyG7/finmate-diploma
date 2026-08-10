from django import forms
from django.utils import timezone

from advisor.models import SavingGoal, GoalContribution
from personal_finance.models import Wallet


class SavingGoalForm(forms.ModelForm):
    class Meta:
        model = SavingGoal
        fields = ["title", "target_amount", "target_date", "start_amount", "priority", "status", "notes"]
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control"
            else:
                css = "form-control"
            field.widget.attrs["class"] = css

    def clean_target_date(self):
        value = self.cleaned_data["target_date"]
        if value < timezone.now().date():
            raise forms.ValidationError("Срок цели не может быть в прошлом.")
        return value


class GoalContributionForm(forms.ModelForm):
    class Meta:
        model = GoalContribution
        fields = ["amount", "date", "wallet", "comment"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"

        if user:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, is_active=True)
        self.fields["wallet"].empty_label = "Выберите счет для списания"