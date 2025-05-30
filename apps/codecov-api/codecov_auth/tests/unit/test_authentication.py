from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, call, patch

import pytest
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIRequestFactory

from codecov_auth.authentication import (
    InternalTokenAuthentication,
    SuperTokenAuthentication,
    UserTokenAuthentication,
)
from codecov_auth.authentication.types import (
    InternalToken,
    InternalUser,
    SuperToken,
    SuperUser,
)
from shared.django_apps.codecov_auth.tests.factories import (
    OwnerFactory,
    UserFactory,
    UserTokenFactory,
)
from shared.django_apps.core.tests.factories import RepositoryFactory


class UserTokenAuthenticationTests(TestCase):
    def test_bearer_token_auth(self):
        user_token = UserTokenFactory()

        request_factory = APIRequestFactory()
        request = request_factory.get(
            "", HTTP_AUTHORIZATION=f"Bearer {user_token.token}"
        )

        authenticator = UserTokenAuthentication()
        result = authenticator.authenticate(request)
        assert result == (user_token.owner, user_token)

    def test_bearer_token_auth_invalid_token(self):
        request_factory = APIRequestFactory()
        request = request_factory.get(
            "", HTTP_AUTHORIZATION="Bearer 8f9bc6cb-fd14-43bc-bbb5-be1e7c948f34"
        )

        authenticator = UserTokenAuthentication()
        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(request)

    def test_token_not_uuid(self):
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION="Bearer hello_world")
        authenticator = UserTokenAuthentication()
        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(request)

    def test_bearer_token_auth_expired_token(self):
        user_token = UserTokenFactory(valid_until=datetime.now() - timedelta(seconds=1))

        request_factory = APIRequestFactory()
        request = request_factory.get(
            "", HTTP_AUTHORIZATION=f"Bearer {user_token.token}"
        )

        authenticator = UserTokenAuthentication()
        with pytest.raises(AuthenticationFailed):
            authenticator.authenticate(request)

    def test_bearer_token_auth_malformed_header(self):
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION="wrong")

        authenticator = UserTokenAuthentication()
        result = authenticator.authenticate(request)
        assert result is None

    def test_bearer_token_auth_no_authorization_header(self):
        request_factory = APIRequestFactory()
        request = request_factory.get("")

        authenticator = UserTokenAuthentication()
        result = authenticator.authenticate(request)
        assert result is None


class SuperTokenAuthenticationTests(TestCase):
    @override_settings(SUPER_API_TOKEN="17603a9e-0463-45e1-883e-d649fccf4ae8")
    def test_bearer_token_auth_if_token_is_super_token(self):
        super_token = "17603a9e-0463-45e1-883e-d649fccf4ae8"

        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {super_token}")

        authenticator = SuperTokenAuthentication()
        result = authenticator.authenticate(request)
        assert isinstance(result[0], SuperUser)
        assert isinstance(result[1], SuperToken)
        assert result[1].token == super_token

    @override_settings(SUPER_API_TOKEN="17603a9e-0463-45e1-883e-d649fccf4ae8")
    def test_bearer_token_auth_invalid_super_token(self):
        super_token = "0ae68e58-79f8-4341-9531-55aada05a251"
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {super_token}")

        authenticator = SuperTokenAuthentication()
        result = authenticator.authenticate(request)
        assert result is None

    def test_bearer_token_default_token_envar(self):
        super_token = "0ae68e58-79f8-4341-9531-55aada05a251"
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {super_token}")
        authenticator = SuperTokenAuthentication()
        result = authenticator.authenticate(request)
        assert result is None

    def test_bearer_token_default_token_envar_and_same_string_as_header(self):
        super_token = settings.SUPER_API_TOKEN
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {super_token}")
        authenticator = SuperTokenAuthentication()
        with pytest.raises(
            AuthenticationFailed,
            match="Invalid token header. Token string should not contain spaces.",
        ):
            authenticator.authenticate(request)


class InternalTokenAuthenticationTests(TestCase):
    @override_settings(CODECOV_INTERNAL_TOKEN="17603a9e-0463-45e1-883e-d649fccf4ae8")
    def test_bearer_token_auth_if_token_is_internal_token(self):
        internal_token = "17603a9e-0463-45e1-883e-d649fccf4ae8"

        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {internal_token}")

        authenticator = InternalTokenAuthentication()
        result = authenticator.authenticate(request)
        assert isinstance(result[0], InternalUser)
        assert isinstance(result[1], InternalToken)
        assert result[1].token == internal_token

    @override_settings(CODECOV_INTERNAL_TOKEN="17603a9e-0463-45e1-883e-d649fccf4ae8")
    def test_bearer_token_auth_if_token_is_not_internal_token(self):
        internal_token = "random_token"

        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {internal_token}")

        authenticator = InternalTokenAuthentication()
        with pytest.raises(
            AuthenticationFailed,
            match="Invalid token",
        ):
            authenticator.authenticate(request)

    def test_bearer_token_default_token_envar_and_same_string_as_header(self):
        internal_token = settings.CODECOV_INTERNAL_TOKEN
        request_factory = APIRequestFactory()
        request = request_factory.get("", HTTP_AUTHORIZATION=f"Bearer {internal_token}")
        authenticator = InternalTokenAuthentication()
        with pytest.raises(
            AuthenticationFailed,
            match="Invalid token header. Token string should not contain spaces.",
        ):
            authenticator.authenticate(request)


class ImpersonationTests(TestCase):
    def setUp(self):
        self.owner_to_impersonate = OwnerFactory(
            username="impersonateme", service="github", user=UserFactory(is_staff=False)
        )
        self.staff_user = UserFactory(is_staff=True)
        self.non_staff_user = UserFactory(is_staff=False)

        self.client.cookies = SimpleCookie({"staff_user": self.owner_to_impersonate.pk})

    def test_impersonation(self):
        self.client.force_login(user=self.staff_user)
        res = self.client.post(
            "/graphql/gh",
            {"query": "{ me { user { username } } }"},
            content_type="application/json",
        )
        assert res.json()["data"]["me"] == {"user": {"username": "impersonateme"}}

    @patch("core.commands.repository.repository.RepositoryCommands.fetch_repository")
    def test_impersonation_with_okta(
        self, mock_call_to_fetch_repository, new_callable=AsyncMock
    ):
        repo = RepositoryFactory(author=self.owner_to_impersonate, private=True)
        query_repositories = """{ owner(username: "%s") { repository(name: "%s") { ... on Repository { name } } } }"""
        query = query_repositories % (repo.author.username, repo.name)

        # not impersonating
        del self.client.cookies["staff_user"]
        self.client.force_login(user=self.owner_to_impersonate.user)
        self.client.post(
            "/graphql/gh",
            {"query": query},
            content_type="application/json",
        )

        # impersonating, same query
        self.client.cookies = SimpleCookie({"staff_user": self.owner_to_impersonate.pk})
        self.client.force_login(user=self.staff_user)
        self.client.post(
            "/graphql/gh",
            {"query": query},
            content_type="application/json",
        )

        mock_call_to_fetch_repository.assert_has_calls(
            [
                call(
                    self.owner_to_impersonate,
                    repo.name,
                    [],
                    exclude_okta_enforced_repos=True,
                    needs_coverage=False,
                    needs_commits=False,
                ),
                call(
                    self.owner_to_impersonate,
                    repo.name,
                    [],
                    exclude_okta_enforced_repos=False,
                    needs_coverage=False,
                    needs_commits=False,
                ),
            ]
        )

    def test_impersonation_non_staff(self):
        self.client.force_login(user=self.non_staff_user)
        with pytest.raises(PermissionDenied):
            self.client.get("/")

    def test_impersonation_invalid_user(self):
        self.client.cookies = SimpleCookie({"staff_user": 9999})
        self.client.force_login(user=self.staff_user)
        with pytest.raises(AuthenticationFailed):
            self.client.get("/")
