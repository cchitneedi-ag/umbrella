from django.test import TestCase

from graphql_api.tests.helper import GraphQLTestHelper
from shared.django_apps.core.tests.factories import OwnerFactory

query = """
mutation($input: RegenerateOrgUploadTokenInput!) {
  regenerateOrgUploadToken(input: $input) {
    orgUploadToken
    error {
      __typename
    }
  }
}
"""


class RegenerateOrgUploadToken(GraphQLTestHelper, TestCase):
    def setUp(self):
        self.owner = OwnerFactory(
            username="codecov", plan="users-enterprisem", service="github"
        )

    def test_when_unauthenticated_error(self):
        data = self.gql_request(query, variables={"input": {"owner": "codecov"}})
        assert (
            data["regenerateOrgUploadToken"]["error"]["__typename"]
            == "UnauthenticatedError"
        )

    def test_when_validation_error(self):
        owner = OwnerFactory(name="rula")
        data = self.gql_request(
            query,
            owner=owner,
            variables={"input": {"owner": "random"}},
        )
        assert (
            data["regenerateOrgUploadToken"]["error"]["__typename"] == "ValidationError"
        )

    def test_when_authenticated_regenerate_token(self):
        data = self.gql_request(
            query,
            owner=self.owner,
            variables={"input": {"owner": "codecov"}},
        )
        newToken = data["regenerateOrgUploadToken"]["orgUploadToken"]
        assert newToken
