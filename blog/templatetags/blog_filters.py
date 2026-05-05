import markdown
import bleach
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='markdown_to_html')
def markdown_to_html(value: str) -> str:
    """
    Конвертирует Markdown в безопасный HTML.
    """
    if not value:
        return ""

    # 1. Расширения (Extensions)
    # extra: включает таблицы, сноски и другие полезные штуки
    # toc: позволяет генерировать оглавление
    # nl2br: переводит переносы строк в <br>
    extensions = ['extra', 'toc', 'nl2br']

    # 2. Конвертация
    html = markdown.markdown(value, extensions=extensions)

    # 3. "Отбеливание" (Bleach) - ЗАЩИТА ОТ XSS
    # Мы разрешаем только безопасные теги и атрибуты. 
    # Если кто-то вставит <script>alert('Hacked')</script>, bleach его удалит или экранирует.
    allowed_tags = [
        'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'ul',
        'strong', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'br', 'hr', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]
    allowed_attrs = {
        'a': ['href', 'title'],
        'abbr': ['title'],
        'acronym': ['title'],
        'img': ['src', 'alt', 'title', 'width', 'height'], # Разрешаем атрибуты для картинок
    }

    cleaned_html = bleach.clean(
        html, 
        tags=allowed_tags, 
        attributes=allowed_attrs, 
        strip=True
    )

    # 4. mark_safe
    # Django по умолчанию экранирует весь вывод. 
    # mark_safe говорит: "Я проверил этот HTML, он чист, выводи его как теги".
    return mark_safe(cleaned_html)