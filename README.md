# FinMate

Веб-приложение для учета личных финансов (доходы/расходы, фильтры, аналитика по категориям).

## Стек
- Python 3.12+
- Django 5.2.8
- SQLite (по умолчанию)

## Возможности
- Регистрация и авторизация пользователей
- Личный кабинет и аватар
- CRUD транзакций (доход/расход)
- Фильтрация транзакций по периоду, типу и категориям
- Аналитика по категориям (Chart.js)
- Сброс и смена пароля

## Быстрый старт

### 1) Клонировать репозиторий
```bash
git clone https://github.com/DmitriyG7/finmate-diploma.git
cd finmate
```

### 2) Создать и активировать виртуальное окружение
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 3) Установить зависимости
```bash
pip install -r requirements.txt
```

### 4) Настроить переменные окружения
Создай .env по примеру .env.example и заполни значения.

### 5) Применить миграции и запустить сервер
```bash
python manage.py migrate
python manage.py runserver

#Открыть в браузере: http://127.0.0.1:8000/
```

### Переменные окружения
Пример в .env.example:

DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
EMAIL_HOST
EMAIL_PORT
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
EMAIL_USE_SSL

### Структура проекта
finmate/ — настройки проекта Django
users/ — пользователи, аутентификация, профиль
personal_finance/ — транзакции, фильтры, аналитика
templates/ — базовые шаблоны

# Статус
Проект в активной доработке (дипломный проект).