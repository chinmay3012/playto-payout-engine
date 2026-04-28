import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'insecure-dev-key')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'apps.payouts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.parse(
        os.getenv('DATABASE_URL', 'sqlite:///' + str(BASE_DIR / 'db.sqlite3')),
        conn_max_age=600,
    )
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
    DATABASES['default'].setdefault('OPTIONS', {})
    DATABASES['default']['OPTIONS']['timeout'] = 30

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '120/min',
    },
}

JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
JWT_ACCESS_TOKEN_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_MINUTES', '60'))
JWT_REFRESH_TOKEN_MINUTES = int(os.getenv('JWT_REFRESH_TOKEN_MINUTES', '43200'))
JWT_ACCESS_COOKIE_NAME = os.getenv('JWT_ACCESS_COOKIE_NAME', 'playto_access')
JWT_REFRESH_COOKIE_NAME = os.getenv('JWT_REFRESH_COOKIE_NAME', 'playto_refresh')
JWT_COOKIE_SECURE = os.getenv('JWT_COOKIE_SECURE', 'False').lower() == 'true'
JWT_COOKIE_SAMESITE = os.getenv('JWT_COOKIE_SAMESITE', 'Lax')

CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173').split(',')
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173').split(',')
CSRF_COOKIE_SECURE = JWT_COOKIE_SECURE
SESSION_COOKIE_SECURE = JWT_COOKIE_SECURE

ALLOW_LEGACY_WRITE_WITHOUT_API_KEY = os.getenv(
    'ALLOW_LEGACY_WRITE_WITHOUT_API_KEY', 'True' if DEBUG else 'False'
).lower() == 'true'

default_broker_url = f"sqla+sqlite:///{BASE_DIR / 'celery_broker.sqlite3'}"
default_result_backend = f"db+sqlite:///{BASE_DIR / 'celery_results.sqlite3'}"

CELERY_BROKER_URL = os.getenv(
    'CELERY_BROKER_URL', os.getenv('REDIS_URL', default_broker_url)
)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', default_result_backend)

def _normalize_sqlite_celery_url(url: str, scheme_prefix: str) -> str:
    marker = f'{scheme_prefix}:///'
    if not url.startswith(marker):
        return url
    path_fragment = url[len(marker):]
    if path_fragment.startswith('/'):
        return url
    return f'{marker}{BASE_DIR / path_fragment}'


CELERY_BROKER_URL = _normalize_sqlite_celery_url(CELERY_BROKER_URL, 'sqla+sqlite')
CELERY_RESULT_BACKEND = _normalize_sqlite_celery_url(CELERY_RESULT_BACKEND, 'db+sqlite')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'retry-stuck-payouts': {
        'task': 'apps.payouts.tasks.retry_stuck_payouts',
        'schedule': 30.0,
    },
    'dispatch-outbox-events': {
        'task': 'apps.payouts.tasks.dispatch_outbox_events',
        'schedule': 5.0,
    },
}
