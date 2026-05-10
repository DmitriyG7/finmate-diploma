from django import forms
from django.forms import ModelChoiceField
from django.forms.widgets import TextInput, Select, Textarea

from personal_finance.models import Category
from .models import Post

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["title", "content", "post_type", "status", "linked_category"]

        widgets = {
            'title': TextInput(attrs={'class': 'form-control'}),
            'content': Textarea(attrs={'class': 'form-control', "rows": 10}),
            'linked_category': Select(attrs={'class': 'form-select'}),
            'post_type': Select(attrs={'class': 'form-select'}),
            'status': Select(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated:
            if not user.is_staff:
                self.fields["status"].choices = [
                    (Post.StatusType.DRAFT, "Черновик"),
                    (Post.StatusType.CHECKING, "Отправить на проверку")
                ]

                self.fields['post_type'].widget = forms.HiddenInput()
                self.initial['post_type'] = Post.PostType.COMMUNITY

            self.fields['linked_category'].queryset = Category.objects.base_categories()
            category_choices = [("", "Выберите категорию")]
            for cat in self.fields["linked_category"].queryset:
                category_choices.append((cat.id, cat.name))

            self.fields["linked_category"].choices = category_choices

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if len(content.strip()) < 50:
            raise forms.ValidationError("Статья слишком короткая! Опишите тему подробнее.")
        return content