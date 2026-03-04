from datetime import timedelta
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "corsheaders",
    # local
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Разреши фронту доступ
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://aristokrat-app.netlify.app",
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://aristokrat-app.netlify.app",
]

# По желанию, но полезно:
CORS_ALLOW_HEADERS = list(sorted(set([
    "authorization", "content-type", "accept", "origin",
    "x-csrftoken", "x-requested-with",
])))
CORS_EXPOSE_HEADERS = ["Content-Type", "Authorization"]

# === Cookies для кросс-домена ===
# Для production (https) » True / "None". На localhost по http "None" не работает;
# поэтому: в DEV можно СДЕЛАТЬ fallback: если DEBUG=True, то Lax+False.
if DEBUG:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"

ROOT_URLCONF = "aristokrat_backend.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "aristokrat_backend.wsgi.application"

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # папка, куда collectstatic всё сложит

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# ============= JAZZMIN CONFIG =============
JAZZMIN_SETTINGS = {
    "site_title": "Аристократ",
    "site_header": "Аристократ - Администрация",
    "site_brand": "Аристократ",
    "site_logo": None,
    "welcome_sign": "Добро пожаловать в панель администратора",
    "copyright": "Аристократ © 2024-2025",
    
    # Цветовая схема
    "topmenu_links": [],
    
    "show_sidebar": True,
    "navigation_expanded": True,
    
    # Боковое меню
    "order_with_respect_to": [
        "api",
        "api.SimpleUser",
        "api.ResidentProfile",
        "api.House",
        "api.Entrance",
        "api.Apartment",
        "api.Device",
    ],
    
    # Кастомизация
    "icons": {
        "auth": "fas fa-user-shield",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        
        "api.SimpleUser": "fas fa-users",
        "api.ResidentProfile": "fas fa-home",
        "api.House": "fas fa-building",
        "api.Entrance": "fas fa-door-open",
        "api.Apartment": "fas fa-door-closed",
        "api.Device": "fas fa-microchip",
    },
    
    "default_icon_parents": "fas fa-chevron-right",
    "default_icon_children": "fas fa-arrow-right",
    
    # Темы
    "theme": "darkly",
    
    # Колонки в листе
    "list_per_page": 25,
    
    # Язык
    "language_code": "ru",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small": False,
    "footer_small": False,
    "body_small": False,
    "sign_in_page_template": None,
    "welcome_sign": "Добро пожаловать",
    "login_logo": None,
    "login_logo_path": None,
    "admin_header_small": False,
    "sidebar_nav_small_text": False,
    "sidebar_disable_auto_expand": False,
    "related_modal_theme": "dark",
}
