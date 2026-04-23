from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.forms import ModelForm


class LoginUserForm(AuthenticationForm):
    username = forms.CharField(label="Логин")
    password = forms.CharField(widget=forms.PasswordInput(), label="Пароль")

    class Meta:
        model = get_user_model()
        fields = ['username', 'password']


class RegisterUserForm(UserCreationForm):
    # username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={'placeholder':"Введите логин"}))
    # password1 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder':"Введите пароль"}), label="Пароль")
    # password2 = forms.CharField(widget=forms.PasswordInput(), label="Повторите пароль")

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': "Введите логин"}),
            'email': forms.EmailInput(attrs={'placeholder': "Введите E-mail"}),
            'password1': forms.PasswordInput(attrs={'placeholder': "Введите пароль"}),
            'password2': forms.PasswordInput(attrs={'placeholder': "Повторите пароль"}),
        }

        labels = {
            'username': 'Логин',
            'email': 'Почта',
            'password1': 'Пароль',
            'password2': 'Повторите пароль',
        }

    def clean_email(self):
        user_email = self.cleaned_data['email'].lower()
        if get_user_model().objects.filter(email=user_email).exists():
            raise ValidationError("Введенный E-mail уже используется")
        return user_email


class UserPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(widget=forms.PasswordInput(), label="Старый пароль")
    new_password1 = forms.CharField(widget=forms.PasswordInput(), label="Новый пароль")
    new_password2 = forms.CharField(widget=forms.PasswordInput(), label="Повторите пароль")


class ProfileForm(forms.ModelForm):
    username = forms.CharField(disabled=True, label='Логин')
    email = forms.EmailField(disabled=True, label='Адрес электронной почты')
    date_joined = forms.DateField(disabled=True, label='Дата регистрации')
    avatar = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'accept': 'image/*',
            'onchange': 'this.form.submit()',
        })
    )

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name', 'date_joined', 'avatar']
