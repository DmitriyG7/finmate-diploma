from django.contrib.auth import logout, get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from finmate import settings
from .forms import LoginUserForm, RegisterUserForm, UserPasswordChangeForm, ProfileForm


class LoginUser(LoginView):
    template_name = 'users/login.html'
    form_class = LoginUserForm
    success_url = reverse_lazy('home')

class RegisterUser(CreateView):
    form_class = RegisterUserForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')

class UserPasswordChange(PasswordChangeView):
    template_name = 'users/password_change_form.html'
    form_class = UserPasswordChangeForm

class ProfileUser(LoginRequiredMixin, UpdateView):
    template_name = 'users/profile.html'
    form_class = ProfileForm
    success_url = reverse_lazy('users:profile')
    context_object_name = 'user'
    extra_context = {
        'DEFAULT_AVATAR': settings.DEFAULT_AVATAR
    }

    def get_object(self):
        return self.request.user

