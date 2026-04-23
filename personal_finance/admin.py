from django.contrib import admin

from .models import Category, PersonalTransaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name',]

@admin.register(PersonalTransaction)
class PersonalTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'total', 'category', 'date', 'description']
    list_filter = ['user', 'date', 'category']
    search_fields = ['user', 'description']
