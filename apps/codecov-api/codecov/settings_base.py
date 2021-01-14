from utils.config import get_config, get_settings_module, SettingsModule
import os


# SECURITY WARNING: keep the secret key used in production secret!
# TODO: get this out of source control
SECRET_KEY = 'edj+31p-b0#5b4z163d4uyzf9*s7juwgy^lx^!-2=v+y_xadz5'


YAML_SECRET_KEY = b']\xbb\x13\xf9}\xb3\xb7\x03)*0Kv\xb2\xcet'


AUTH_USER_MODEL = 'codecov_auth.Owner'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'core',
    'codecov_auth',
    'internal_api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'codecov.urls'

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

WSGI_APPLICATION = 'codecov.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASE_USER = get_config('services', 'database', 'username', default='postgres')
DATABASE_NAME = get_config('services', 'database', 'name', default='postgres')
DATABASE_PASSWORD = get_config('services', 'database', 'password', default='postgres')
DATABASE_HOST = get_config('services', 'database', 'host', default='postgres')

# this is the time in seconds django decides to keep the connection open after the request
# the default is 0 seconds, meaning django closes the connection after every request
# https://docs.djangoproject.com/en/3.1/ref/settings/#conn-max-age
CONN_MAX_AGE = int(get_config('services', 'database', 'conn_max_age', default=0))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': DATABASE_NAME,
        'USER': DATABASE_USER,
        'PASSWORD': DATABASE_PASSWORD,
        'HOST': DATABASE_HOST,
        'PORT': '5432',
        'CONN_MAX_AGE': CONN_MAX_AGE
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

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


REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'codecov_auth.authentication.CodecovSessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',),
    'PAGE_SIZE': 20
}


# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = '/static/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(message)s %(asctime)s %(name)s %(levelname)s %(lineno)s %(pathname)s %(funcName)s %(threadName)s',
            'class': 'utils.logging.CustomLocalJsonFormatter'
        },
        'json': {
            'format': '%(message)s %(asctime)s %(name)s %(levelname)s %(lineno)s %(pathname)s %(funcName)s %(threadName)s',
            'class': 'utils.logging.CustomDatadogJsonFormatter'
        },
    },
    'root': {
        'handlers': ['default'],
        'level': 'INFO',
        'propagate': True
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'formatter': 'standard' if get_settings_module() == SettingsModule.DEV.value else 'json',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',  # Default is stderr
        },
    },
    'loggers': {}
}

MINIO_ACCESS_KEY = get_config('services', 'minio', 'access_key_id')
MINIO_SECRET_KEY = get_config('services', 'minio', 'secret_access_key')
MINIO_LOCATION = 'codecov.s3.amazonaws.com'
MINIO_HASH_KEY = get_config('services', 'minio', 'hash_key')
ARCHIVE_BUCKET_NAME = 'codecov'
ENCRYPTION_SECRET = get_config('setup', 'encryption_secret')

COOKIE_SECRET = get_config("setup", "http", "cookie_secret")
COOKIES_DOMAIN = ".codecov.io"

CIRCLECI_TOKEN = os.environ.get("CIRCLECI__TOKEN")

GITHUB_CLIENT_ID = os.environ.get("GITHUB__CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB__CLIENT_SECRET")
GITHUB_CLIENT_BOT = os.environ.get("GITHUB__CLIENT_BOT")
GITHUB_ACTIONS_TOKEN = os.environ.get("GITHUB__ACTIONS_TOKEN")

BITBUCKET_CLIENT_ID = os.environ.get("BITBUCKET__CLIENT_ID")
BITBUCKET_CLIENT_SECRET = os.environ.get("BITBUCKET__CLIENT_SECRET")
BITBUCKET_CLIENT_BOT = os.environ.get("BITBUCKET__CLIENT_BOT")

GITLAB_CLIENT_ID = os.environ.get("GITLAB__CLIENT_ID")
GITLAB_CLIENT_SECRET = os.environ.get("GITLAB__CLIENT_SECRET")
GITLAB_REDIRECT_URI = "https://codecov.io/login/gitlab"
GITLAB_CLIENT_BOT = os.environ.get("GITLAB__CLIENT_BOT")


SEGMENT_API_KEY = get_config('setup', 'segment', 'key', default=None)
SEGMENT_ENABLED = get_config('setup', 'segment', 'enabled', default=False) and not bool(get_config('setup', 'enterprise_license', default=False))

IS_ENTERPRISE = get_settings_module() == SettingsModule.ENTERPRISE.value
