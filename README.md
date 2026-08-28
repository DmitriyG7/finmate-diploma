# FinMate

Веб-приложение для управления личными финансами: учёт доходов и расходов, кошельки, переводы, аналитика, цели накоплений, блог и уведомления.

## Стек технологий

- **Python** 3.12+
- **Django** 5.2.8
- **SQLite** (по умолчанию)
- **Bootstrap 5**, Chart.js, Flatpickr (через шаблоны)

## Возможности

- регистрация, авторизация (логин и email), профиль с аватаром;
- кошельки, категории, транзакции (доход / расход / перевод);
- совместный доступ к кошелькам;
- аналитика по категориям;
- финансовые цели и рекомендации (advisor);
- блог с модерацией публикаций;
- лайки, комментарии, уведомления.

---

## Требования

Перед запуском убедитесь, что установлены:

- Python 3.12 или новее;
- Git;
- pip (обычно идёт вместе с Python).

Проверка версии Python:

```bash
python --version
```

---

## Быстрый старт (локальный запуск)

Все команды ниже выполняются из корня проекта — папки, где лежит `manage.py`.

### 1. Клонировать репозиторий

```bash
git clone https://github.com/DmitriyG7/finmate-diploma.git
cd finmate-diploma
```

Если репозиторий уже скачан, перейдите в папку проекта:

```bash
cd finmate
```

### 2. Создать и активировать виртуальное окружение

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Установить зависимости

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

Скопируйте пример файла окружения:

**Windows (PowerShell):**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Откройте `.env` и при необходимости измените значения. Для локального запуска достаточно минимальной конфигурации:

```env
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

> Для разработки можно оставить `DJANGO_DEBUG=True`.  
> Для production обязательно задайте уникальный `DJANGO_SECRET_KEY` и `DJANGO_DEBUG=False`.

### 5. Применить миграции

```bash
python manage.py migrate
```

### 6. (Опционально) Создать администратора

Нужно для входа в Django Admin (`/admin/`):

```bash
python manage.py createsuperuser
```

### 7. Запустить сервер разработки

```bash
python manage.py runserver
```

Откройте в браузере: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Основные URL

| URL | Назначение |
|-----|------------|
| `/` | Главная: транзакции |
| `/users/login/` | Вход |
| `/users/register/` | Регистрация |
| `/users/profile/` | Профиль |
| `/advisor/` | Финансовые цели |
| `/posts/` | Блог |
| `/notifications/` | Уведомления |
| `/admin/` | Панель администратора |

---

## Переменные окружения

| Переменная | Обязательна | Описание | Пример |
|------------|-------------|----------|--------|
| `DJANGO_SECRET_KEY` | Да (для production) | Секретный ключ Django | `django-insecure-...` |
| `DJANGO_DEBUG` | Нет | Режим отладки | `True` |
| `DJANGO_ALLOWED_HOSTS` | Нет | Разрешённые хосты через запятую | `127.0.0.1,localhost` |
| `EMAIL_HOST` | Нет | SMTP-сервер | `smtp.mail.ru` |
| `EMAIL_PORT` | Нет | Порт SMTP | `465` |
| `EMAIL_HOST_USER` | Нет | Email для отправки писем | `user@mail.ru` |
| `EMAIL_HOST_PASSWORD` | Нет | Пароль SMTP | `app-password` |
| `EMAIL_USE_SSL` | Нет | Использовать SSL | `True` |
| `MAX_WALLETS_PER_USER` | Нет | Лимит кошельков на пользователя | `10` |

Файл `.env` загружается автоматически при старте приложения.

### Email (сброс пароля)

Для работы сброса пароля по email заполните SMTP-переменные в `.env`.  
Без них регистрация и основной функционал работают, но письма отправляться не будут.

---

## Структура проекта

```text
finmate/
├── manage.py
├── requirements.txt
├── .env.example
├── finmate/                 # Настройки Django (settings, urls, wsgi)
├── users/                   # Пользователи, авторизация, профиль
├── personal_finance/        # Кошельки, транзакции, аналитика
├── advisor/                 # Цели накоплений и рекомендации
├── blog/                    # Публикации и модерация
├── interactions/            # Лайки и комментарии
├── notifications/           # Уведомления
├── groups/                  # Заготовка под групповой функционал
├── templates/               # Общие шаблоны
├── static/                  # Общие статические файлы
└── media/                   # Загружаемые файлы (аватары и т.д.)
```

---

## Полезные команды

```bash
# Проверка конфигурации Django
python manage.py check

# Создание новых миграций (при изменении моделей)
python manage.py makemigrations

# Применение миграций
python manage.py migrate

# Запуск на другом порту
python manage.py runserver 8080

# Сбор статики (для production)
python manage.py collectstatic
```

---

## Возможные проблемы

### `ModuleNotFoundError` при запуске

Убедитесь, что виртуальное окружение активировано и зависимости установлены:

```bash
pip install -r requirements.txt
```

### Ошибка активации venv в PowerShell (Windows)

Выполните (один раз от администратора):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### `no such table` или ошибки БД

Примените миграции:

```bash
python manage.py migrate
```

### Статика или медиа не отображаются

В режиме `DEBUG=True` медиафайлы раздаются автоматически.  
Папка `media/` создаётся при загрузке аватаров и других файлов.

### Письма не отправляются

Проверьте SMTP-настройки в `.env`. Для локальной разработки можно временно использовать консольный backend в `settings.py`:

```python
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

---

## Проверка работоспособности (чеклист для ревьюера)

1. Установить зависимости: `pip install -r requirements.txt`
2. Создать `.env` из `.env.example`
3. Выполнить `python manage.py migrate`
4. Запустить `python manage.py runserver`
5. Открыть [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
6. Зарегистрировать пользователя и войти в систему
7. Создать кошелёк и добавить тестовую транзакцию
8. (Опционально) создать superuser и проверить `/admin/`

---

## Лицензия и статус

Проект разрабатывается в рамках дипломной работы.  
Для вопросов по запуску или демонстрации функционала обращайтесь к автору репозитория.
