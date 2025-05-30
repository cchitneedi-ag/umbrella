import json
import logging

import jwt
from django.conf import settings
from django.db.utils import IntegrityError

from codecov_auth.models import Owner
from services.task import TaskService

log = logging.getLogger(__name__)


class SentryError(Exception):
    pass


class SentryInvalidStateError(SentryError):
    """
    The Sentry `state` JWT was malformed or not signed properly.
    """

    pass


class SentryUserAlreadyExistsError(SentryError):
    """
    The Sentry `user_id` was already claimed by a Codecov owner.
    """

    pass


class SentryState:
    def __init__(self, data: dict):
        self.data = data

    @property
    def user_id(self) -> str | None:
        return self.data.get("user_id")


def decode_state(state: str) -> SentryState | None:
    """
    Decode the given state (a JWT) using our shared secret.
    Returns `None` if the state could not be decoded.
    """
    secret = settings.SENTRY_JWT_SHARED_SECRET
    try:
        data = jwt.decode(state, secret, algorithms=["HS256"])
        return SentryState(data)
    except jwt.exceptions.InvalidSignatureError:
        # signed with a different secret
        log.error(
            "Sentry state has invalid signature",
            extra={"sentry_state": state},
        )
        return None
    except jwt.exceptions.DecodeError:
        # malformed JWT
        log.error(
            "Sentry state is malformed",
            extra={"sentry_state": state},
        )
        return None


def save_sentry_state(owner: Owner, encoded_state: str):
    """
    If the given state decodes successfully then save it with the owner.
    """
    decoded_state = decode_state(encoded_state)
    if decoded_state is None:
        log.error(
            "Invalid Sentry state",
            extra={"owner_id": owner.pk, "sentry_state": encoded_state},
        )
        raise SentryInvalidStateError()

    if decoded_state.user_id is not None:
        owner.sentry_user_id = decoded_state.user_id
    owner.sentry_user_data = decoded_state.data

    try:
        owner.save()
    except IntegrityError:
        log.error(
            "Sentry user already exists",
            extra={
                "owner_id": owner.pk,
                "sentry_user_id": decoded_state.user_id,
                "sentry_user_data": decoded_state.data,
            },
        )
        raise SentryUserAlreadyExistsError()


def is_sentry_user(owner: Owner) -> bool:
    """
    Returns true if the given owner has been linked with a Sentry user.
    """
    return owner.sentry_user_id is not None


def send_user_webhook(user: Owner, org: Owner):
    """
    Sends data back to Sentry about the Sentry <-> Codecov user link.
    """
    assert is_sentry_user(user)

    webhook_url = settings.SENTRY_USER_WEBHOOK_URL
    if webhook_url is None:
        log.warning("No Sentry webhook URL is configured")
        return

    state = {
        "user_id": user.sentry_user_id,
        "org_id": (user.sentry_user_data or {}).get("org_id"),
        "codecov_owner_id": user.pk,
        "codecov_organization_id": org.pk,
        "service": org.service,
        "service_id": org.service_id,
    }

    secret = settings.SENTRY_JWT_SHARED_SECRET
    encoded_state = jwt.encode(state, secret, algorithm="HS256")

    payload = json.dumps({"state": encoded_state})

    TaskService().http_request(
        url=webhook_url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Codecov",
        },
        data=payload,
    )
