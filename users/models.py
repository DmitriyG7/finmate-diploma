from django.contrib.auth.models import AbstractUser
from django.db import models


class Currency(models.TextChoices):
    RUB = 'RUB', 'Рубль'
    USD = 'USD', 'Доллар США'
    EUR = 'EUR', 'Евро'


class User(AbstractUser):
    avatar = models.FileField(upload_to='avatars/', blank=True, null=True)
    preferred_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.RUB)
    settings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.username
