from django.contrib.auth.models import AbstractUser
from django.db import models


CURRENCY_CHOICES = [
        ('RUB', 'Ruble'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
    ]

class User(AbstractUser):
    avatar = models.FileField(upload_to='avatars/', blank=True, null=True)
    preferred_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='RUB')
    settings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.username
