"""
Django settings for config project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'apps',
    'apps.dart',
    'apps.ecos',
    'apps.companies',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 10,  # SQLite 잠금 대기(초). 짧게 두면 실패 후 save_company_to_db 재시도(0.5~2초 sleep)가 빨리 동작
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'ko-kr'

TIME_ZONE = 'Asia/Seoul'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# API Keys (from .env)
DART_API_KEY = os.getenv('DART_API_KEY', '')
ECOS_API_KEY = os.getenv('ECOS_API_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
KRX_API_KEY = os.getenv('KRX_API_KEY', '')
# KRX 시가총액 조회 서비스 URL (Spec.docx/개발명세서 기준으로 .env에서 오버라이드 가능)
KRX_BASE_URL = os.getenv('KRX_BASE_URL', 'https://openapi.krx.co.kr')

# 데이터 수집 설정 (환경변수 또는 기본값)
DATA_COLLECTION = {
    # API 관련
    'API_TIMEOUT': int(os.getenv('API_TIMEOUT', '30')),  # API 요청 타임아웃 (초)
    'API_MAX_RETRIES': int(os.getenv('API_MAX_RETRIES', '2')),  # 최대 재시도 횟수
    'API_DELAY': float(os.getenv('API_DELAY', '3.0')),  # API 호출 후 지연(초). 병렬 시 rate limit 완화용.
    
    # 데이터 수집 관련
    'COLLECTION_LIMIT': int(os.getenv('COLLECTION_LIMIT', '10')),
    # 기업 배치 병렬 수집 스레드 수 (1=순차). 2 이상이면 스레드별 DB 연결로 SQLite "database is locked" 가능 → save_company_to_db에서 자동 재시도.
    'PARALLEL_WORKERS': int(os.getenv('PARALLEL_WORKERS', '9')),

    # 로깅
    'LOGGING_LEVEL': os.getenv('LOGGING_LEVEL', 'INFO'),  # 로깅 레벨
}

# 재무 지표 계산기 기본값 (환경변수로 오버라이드 가능)
CALCULATOR_DEFAULTS = {
    'TAX_RATE': int(os.getenv('CALCULATOR_TAX_RATE', '25')),  # 법인세율 (%)
    'EQUITY_RISK_PREMIUM': float(os.getenv('CALCULATOR_EQUITY_RISK_PREMIUM', '10.0')),  # 주주기대수익률 (%)
}

# 2차 필터: ROIC - WACC >= 이 값(소수, 0.02 = 2%)이면 통과
SECOND_FILTER_ROIC_WACC_SPREAD = float(os.getenv('SECOND_FILTER_ROIC_WACC_SPREAD', '0.02'))

# 로깅: formatter, console handler, root logger 통일
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '%(levelname)s [%(name)s] %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
        },
    },
    'root': {
        'level': DATA_COLLECTION['LOGGING_LEVEL'],
        'handlers': ['console'],
    },
}
