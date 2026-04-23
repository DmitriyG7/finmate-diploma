from django.conf import settings
from django.db import models


class Category(models.Model):
    class OperationType(models.TextChoices):
        INCOME = 'income', 'Доход'
        EXPENSE = 'expense', 'Расход'

    name = models.CharField(max_length=255, unique=True, verbose_name="Имя категории")

    def __str__(self):
        return f"{self.name}"


class PersonalTransaction(models.Model):
    class OperationType(models.TextChoices):
        INCOME = 'income', 'Доход'
        EXPENSE = 'expense', 'Расход'

    total = models.DecimalField(max_digits=10, decimal_places=2, null=False, verbose_name="Сумма")
    date = models.DateField(verbose_name="Дата")
    description = models.TextField(blank=True, verbose_name="Описание")
    category = models.ForeignKey('Category', on_delete=models.CASCADE, verbose_name="Категория",
                                 related_name='category_transactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь",
                             related_name='transactions')
    operation_type = models.CharField(max_length=7, default=OperationType.EXPENSE,
                                      choices=OperationType.choices)

    def __str__(self):
        return f"{self.user.username} - {self.total} - {self.category.name}"
