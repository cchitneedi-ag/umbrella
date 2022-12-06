import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from .settings_base import *

DEBUG = False
THIS_POD_IP = os.environ.get("THIS_POD_IP")
ALLOWED_HOSTS = get_config(
    "setup", "api_allowed_hosts", default=["stage-api.codecov.dev"]
)
if THIS_POD_IP:
    ALLOWED_HOSTS.append(THIS_POD_IP)

WEBHOOK_URL = get_config(
    "setup", "webhook_url", default="https://stage-api.codecov.dev"
)

STRIPE_API_KEY = os.environ.get("SERVICES__STRIPE__API_KEY", None)
STRIPE_ENDPOINT_SECRET = os.environ.get("SERVICES__STRIPE__ENDPOINT_SECRET", None)
COOKIES_DOMAIN = ".codecov.dev"
SESSION_COOKIE_DOMAIN = ".codecov.dev"
STRIPE_PLAN_IDS = {
    "users-pr-inappm": "plan_H6P3KZXwmAbqPS",
    "users-pr-inappy": "plan_H6P16wij3lUuxg",
}

sentry_sdk.init(
    dsn=os.environ.get("SERVICES__SENTRY__SERVER_DSN", None),
    integrations=[
        DjangoIntegration(),
        CeleryIntegration(),
        RedisIntegration(),
        HttpxIntegration(),
    ],
    environment="STAGING",
    traces_sample_rate=float(os.environ.get("SERVICES__SENTRY__SAMPLE_RATE", 1)),
    _experiments={
        "profiles_sample_rate": float(
            os.environ.get("SERVICES__SENTRY__PROFILE_SAMPLE_RATE", 1.0)
        ),
    },
)
CORS_ALLOW_HEADERS += ["sentry-trace", "baggage"]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^(https:\/\/)?deploy-preview-\d+--codecov\.netlify\.app$",
    r"^(https:\/\/)?deploy-preview-\d+--stage-app\.netlify\.app$",
    r"^(https:\/\/)?deploy-preview-\d+--codecov-stage\.netlify\.app$",
    r"^(https:\/\/)?deploy-preview-\d+--gazebo\.netlify\.app$",
    r"^(https:\/\/)?deploy-preview-\d+--gazebo-staging\.netlify\.app$",
    r"^(https:\/\/)?\w+--gazebo\.netlify\.app$",
]
CORS_ALLOW_CREDENTIALS = True

CODECOV_URL = get_config(
    "setup", "codecov_url", default="https://stage-web.codecov.dev"
)
CODECOV_DASHBOARD_URL = get_config(
    "setup", "codecov_dashboard_url", default="https://stage-app.codecov.dev"
)
CORS_ALLOWED_ORIGINS = [
    CODECOV_URL,
    CODECOV_DASHBOARD_URL,
    "https://gazebo.netlify.app",
    "https://gazebo-staging.netlify.app",
    "http://localhost:3000",
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 15000000

# Same site is set to none on Staging as we want to be able to call the API
# From Netlify preview deploy
COOKIE_SAME_SITE = "None"

GRAPHQL_PLAYGROUND = True
