from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    # Автоматически заполняет слаг из заголовка
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_verified',)

    list_display = ('title', 'author', 'post_type', 'is_verified', 'created_at')
    list_filter = ('post_type', 'is_verified', 'created_at')
    search_fields = ('title', 'content')
    raw_id_fields = ('author',)