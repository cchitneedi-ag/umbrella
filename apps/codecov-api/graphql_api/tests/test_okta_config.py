from django.test import TestCase

from shared.django_apps.codecov_auth.tests.factories import (
    AccountFactory,
    OktaSettingsFactory,
    OwnerFactory,
)

from .helper import GraphQLTestHelper


class OktaConfigTestCase(GraphQLTestHelper, TestCase):
    def setUp(self):
        self.account = AccountFactory(name="Test Account")
        self.owner = OwnerFactory(
            username="randomOwner", service="github", account=self.account
        )
        self.okta_settings = OktaSettingsFactory(
            account=self.account,
            client_id="test-client-id",
            client_secret="test-client-secret",
            enabled=True,
            enforced=False,
        )

    def test_fetch_enabled_okta_config(self) -> None:
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account {{
                        oktaConfig {{
                            enabled
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"]["enabled"] == True

    def test_fetch_disabled_okta_config(self) -> None:
        self.okta_settings.enabled = False
        self.okta_settings.save()
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account {{
                        oktaConfig {{
                            enabled
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"]["enabled"] == False

    def test_fetch_enforced_okta_config(self) -> None:
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account {{
                        oktaConfig {{
                            enforced
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"]["enforced"] == False

    def test_fetch_enforced_okta_config_true(self) -> None:
        self.okta_settings.enforced = True
        self.okta_settings.save()
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account {{
                        oktaConfig {{
                            enforced
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"]["enforced"] == True

    def test_fetch_url_okta_config(self) -> None:
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account{{
                        oktaConfig {{
                            url
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"]["url"] == self.okta_settings.url

    def test_fetch_okta_config_client_id(self) -> None:
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account{{
                        oktaConfig {{
                            clientId
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert (
            result["owner"]["account"]["oktaConfig"]["clientId"]
            == self.okta_settings.client_id
        )

    def test_fetch_okta_config_client_secret(self) -> None:
        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                    account{{
                        oktaConfig {{
                            clientSecret
                        }}
                    }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert (
            result["owner"]["account"]["oktaConfig"]["clientSecret"]
            == self.okta_settings.client_secret
        )

    def test_fetch_non_existent_okta_config(self) -> None:
        self.okta_settings.delete()

        query = f"""
            query {{
                owner(username: "{self.owner.username}"){{
                account{{
                    oktaConfig {{
                        clientId
                        clientSecret
                        url
                    }}
                }}
                }}
            }}
        """

        result = self.gql_request(query, owner=self.owner)

        assert "errors" not in result
        assert result["owner"]["account"]["oktaConfig"] is None
