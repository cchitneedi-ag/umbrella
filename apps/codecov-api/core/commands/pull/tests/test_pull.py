from core.models import Pull
from django.test import TransactionTestCase
from unittest.mock import patch

from codecov_auth.tests.factories import OwnerFactory
from core.tests.factories import PullFactory, RepositoryFactory
from ..pull import PullCommands


class PullCommandsTest(TransactionTestCase):
    def setUp(self):
        self.user = OwnerFactory(username="codecov-user")
        self.repository = RepositoryFactory()
        self.command = PullCommands(self.user, "github")

    @patch("core.commands.pull.pull.FetchPullRequestsInteractor.execute")
    def test_fetch_pull_requests_delegate_to_interactor(self, interactor_mock):
        repo = RepositoryFactory()
        self.command.fetch_pull_requests(repo)
        interactor_mock.assert_called_once_with(repo)

    @patch("core.commands.pull.pull.FetchPullRequestInteractor.execute")
    def test_fetch_pull_request_delegate_to_interactor(self, interactor_mock):
        repo = RepositoryFactory()
        self.command.fetch_pull_request(repo, 12)
        interactor_mock.assert_called_once_with(repo, 12)
