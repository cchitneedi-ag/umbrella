import asyncio
from hashlib import sha1
from unittest.mock import patch

from django.test import TransactionTestCase

from billing.constants import BASIC_PLAN_NAME
from codecov_auth.tests.factories import (
    GetAdminProviderAdapter,
    OwnerFactory,
    OwnerProfileFactory,
)
from core.tests.factories import CommitFactory, OwnerFactory, RepositoryFactory
from reports.tests.factories import CommitReportFactory, UploadFactory

from .helper import GraphQLTestHelper, paginate_connection

query_repositories = """{
    owner(username: "%s") {
        orgUploadToken
        hashOwnerid
        isCurrentUserPartOfOrg
        yaml
        repositories%s {
            totalCount
            edges {
                node {
                    name
                }
            }
            pageInfo {
                hasNextPage
                %s
            }
        }
    }
}
"""


class TestOwnerType(GraphQLTestHelper, TransactionTestCase):
    def setUp(self):
        self.user = OwnerFactory(username="codecov-user", service="github")
        random_user = OwnerFactory(username="random-user", service="github")
        RepositoryFactory(
            author=self.user, active=True, activated=True, private=True, name="a"
        )
        RepositoryFactory(
            author=self.user, active=False, private=False, activated=False, name="b"
        )
        RepositoryFactory(
            author=random_user, active=True, activated=False, private=True, name="not"
        )
        RepositoryFactory(
            author=random_user,
            active=True,
            private=False,
            activated=True,
            name="still-not",
        )

    def test_fetching_repositories(self):
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query, user=self.user)
        hash_ownerid = sha1(str(self.user.ownerid).encode())
        hashOwnerid = hash_ownerid.hexdigest()
        assert data == {
            "owner": {
                "orgUploadToken": None,
                "hashOwnerid": hashOwnerid,
                "isCurrentUserPartOfOrg": True,
                "yaml": None,
                "repositories": {
                    "totalCount": 2,
                    "edges": [{"node": {"name": "a"}}, {"node": {"name": "b"}}],
                    "pageInfo": {"hasNextPage": False},
                },
            }
        }

    def test_fetching_repositories_with_pagination(self):
        query = query_repositories % (self.user.username, "(first: 1)", "endCursor")
        # Check on the first page if we have the repository b
        data_page_one = self.gql_request(query, user=self.user)
        connection = data_page_one["owner"]["repositories"]
        assert connection["edges"][0]["node"] == {"name": "a"}
        pageInfo = connection["pageInfo"]
        assert pageInfo["hasNextPage"] == True
        next_cursor = pageInfo["endCursor"]
        # Check on the second page if we have the other repository, by using the cursor
        query = query_repositories % (
            self.user.username,
            f'(first: 1, after: "{next_cursor}")',
            "endCursor",
        )
        data_page_two = self.gql_request(query, user=self.user)
        connection = data_page_two["owner"]["repositories"]
        assert connection["edges"][0]["node"] == {"name": "b"}
        pageInfo = connection["pageInfo"]
        assert pageInfo["hasNextPage"] == False

    def test_fetching_active_repositories(self):
        query = query_repositories % (
            self.user.username,
            "(filters: { active: true })",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "a"}]

    def test_fetching_repositories_by_name(self):
        query = query_repositories % (
            self.user.username,
            '(filters: { term: "a" })',
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "a"}]

    def test_fetching_public_repository_when_unauthenticated(self):
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "b"}]

    def test_fetching_repositories_with_ordering(self):
        query = query_repositories % (
            self.user.username,
            "(ordering: NAME, orderingDirection: DESC)",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "b"}, {"name": "a"}]

    def test_fetching_repositories_inactive_repositories(self):
        query = query_repositories % (
            self.user.username,
            "(filters: { active: false })",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "b"}]

    def test_fetching_repositories_active_repositories(self):
        query = query_repositories % (
            self.user.username,
            "(filters: { active: true })",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "a"}]

    def test_fetching_repositories_activated_repositories(self):
        query = query_repositories % (
            self.user.username,
            "(filters: { activated: true })",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "a"}]

    def test_fetching_repositories_deactivated_repositories(self):
        query = query_repositories % (
            self.user.username,
            "(filters: { activated: false })",
            "",
        )
        data = self.gql_request(query, user=self.user)
        repos = paginate_connection(data["owner"]["repositories"])
        assert repos == [{"name": "b"}]

    def test_is_part_of_org_when_unauthenticated(self):
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query)
        assert data["owner"]["isCurrentUserPartOfOrg"] is False

    def test_is_part_of_org_when_authenticated_but_not_part(self):
        org = OwnerFactory(username="random_org_test", service="github")
        user = OwnerFactory(username="random_org_user", service="github")
        query = query_repositories % (org.username, "", "")
        data = self.gql_request(query, user=user)
        assert data["owner"]["isCurrentUserPartOfOrg"] is False

    def test_is_part_of_org_when_user_asking_for_themself(self):
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["isCurrentUserPartOfOrg"] is True

    def test_is_part_of_org_when_user_path_of_it(self):
        org = OwnerFactory(username="random_org_test", service="github")
        user = OwnerFactory(
            username="random_org_user", service="github", organizations=[org.ownerid]
        )
        query = query_repositories % (org.username, "", "")
        data = self.gql_request(query, user=user)
        assert data["owner"]["isCurrentUserPartOfOrg"] is True

    def test_yaml_when_owner_not_have_yaml(self):
        org = OwnerFactory(username="no_yaml", yaml=None, service="github")
        self.user.organizations = [org.ownerid]
        self.user.save()
        query = query_repositories % (org.username, "", "")
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["yaml"] is None

    def test_yaml_when_current_user_not_part_of_org(self):
        yaml = {"test": "test"}
        org = OwnerFactory(username="no_yaml", yaml=yaml, service="github")
        self.user.organizations = []
        self.user.save()
        query = query_repositories % (org.username, "", "")
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["yaml"] is None

    def test_yaml_return_data(self):
        yaml = {"test": "test"}
        org = OwnerFactory(username="no_yaml", yaml=yaml, service="github")
        self.user.organizations = [org.ownerid]
        self.user.save()
        query = query_repositories % (org.username, "", "")
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["yaml"] == "test: test\n"

    @patch("codecov_auth.commands.owner.owner.OwnerCommands.set_yaml_on_owner")
    def test_repository_dispatch_to_command(self, command_mock):
        asyncio.set_event_loop(asyncio.new_event_loop())
        repo = RepositoryFactory(author=self.user, private=False)
        query_repositories = """{
            owner(username: "%s") {
                repository(name: "%s") {
                    name
                }
            }
        }
        """
        command_mock.return_value = repo
        query = query_repositories % (repo.author.username, repo.name)
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["repository"]["name"] == repo.name

    def test_resolve_number_of_uploads_per_user(self):
        query_uploads_number = """{
            owner(username: "%s") {
               numberOfUploads
            }
        }
        """
        repository = RepositoryFactory.create(
            author__plan=BASIC_PLAN_NAME, author=self.user
        )
        first_commit = CommitFactory.create(repository=repository)
        first_report = CommitReportFactory.create(commit=first_commit)
        for i in range(150):
            UploadFactory.create(report=first_report)
        query = query_uploads_number % (repository.author.username)
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["numberOfUploads"] == 150

    def test_is_current_user_not_an_admin(self):
        query_current_user_is_admin = """{
            owner(username: "%s") {
               isAdmin
            }
        }
        """
        user = OwnerFactory(username="random_org_user", service="github")
        owner = OwnerFactory(username="random_org_test", service="github")
        query = query_current_user_is_admin % (owner.username)
        data = self.gql_request(query, user=user)
        assert data["owner"]["isAdmin"] is False

    @patch(
        "codecov_auth.commands.owner.interactors.get_is_current_user_an_admin.get_provider"
    )
    def test_is_current_user_an_admin(self, mocked_get_adapter):
        query_current_user_is_admin = """{
            owner(username: "%s") {
               isAdmin
            }
        }
        """
        user = OwnerFactory(username="random_org_admin", service="github")
        owner = OwnerFactory(
            username="random_org_test", service="github", admins=[user.ownerid]
        )
        mocked_get_adapter.return_value = GetAdminProviderAdapter()
        query = query_current_user_is_admin % (owner.username)
        data = self.gql_request(query, user=user)
        assert data["owner"]["isAdmin"] is True

    def test_hashOwnerid(self):
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query, user=self.user)
        hash_ownerid = sha1(str(self.user.ownerid).encode())
        hashOwnerid = hash_ownerid.hexdigest()
        assert data["owner"]["hashOwnerid"] == hashOwnerid

    @patch("codecov_auth.commands.owner.owner.OwnerCommands.get_org_upload_token")
    def test_get_org_upload_token(self, mocker):
        mocker.return_value = "upload_token"
        query = query_repositories % (self.user.username, "", "")
        data = self.gql_request(query, user=self.user)
        assert data["owner"]["orgUploadToken"] == "upload_token"

    def test_get_default_org_username_for_owner(self):
        organization = OwnerFactory(username="sample-org", service="github")
        owner = OwnerFactory(
            username="sample-owner",
            service="github",
            organizations=[organization.ownerid],
        )
        OwnerProfileFactory(owner=owner, default_org=organization)
        query = """{
            owner(username: "%s") {
                defaultOrgUsername
                username
            }
        }
        """ % (
            owner.username
        )
        data = self.gql_request(query, user=owner)
        assert data["owner"]["defaultOrgUsername"] == organization.username

    def test_owner_without_default_org_returns_null(self):
        owner = OwnerFactory(username="sample-owner", service="github")
        OwnerProfileFactory(owner=owner, default_org=None)
        query = """{
            owner(username: "%s") {
                defaultOrgUsername
                username
            }
        }
        """ % (
            owner.username
        )
        data = self.gql_request(query, user=owner)
        assert data["owner"]["defaultOrgUsername"] == None

    def test_owner_without_owner_profile_returns_no_default_org(self):
        owner = OwnerFactory(username="sample-owner", service="github")
        query = """{
            owner(username: "%s") {
                defaultOrgUsername
                username
            }
        }
        """ % (
            owner.username
        )
        data = self.gql_request(query, user=owner)
        assert data["owner"]["defaultOrgUsername"] == None

    def test_is_current_user_not_activated(self):
        owner = OwnerFactory(username="sample-owner", service="github")
        query = """{
            owner(username: "%s") {
                isCurrentUserActivated
            }
        }
        """ % (
            owner.username
        )
        data = self.gql_request(query, user=owner)
        assert data["owner"]["isCurrentUserActivated"] == False

    def test_is_current_user_activated(self):
        user = OwnerFactory(username="sample-user")
        owner = OwnerFactory(
            username="sample-owner", plan_activated_users=[user.ownerid]
        )
        query = """{
            owner(username: "%s") {
                isCurrentUserActivated
            }
        }
        """ % (
            owner.username
        )
        data = self.gql_request(query, user=user)
        assert data["owner"]["isCurrentUserActivated"] == True
