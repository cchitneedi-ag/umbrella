from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from core.models import Repository
from shared.django_apps.core.tests.factories import (
    CommitFactory,
    OwnerFactory,
    RepositoryFactory,
)


class RepositoryQuerySetTests(TestCase):
    def setUp(self):
        self.repo1 = RepositoryFactory()
        self.repo2 = RepositoryFactory()

    def test_with_latest_commit_totals_before(self):
        totals = {"n": 10, "h": 5, "m": 3, "p": 2, "c": 100.0, "C": 80.0}
        CommitFactory(totals=totals, repository=self.repo1)

        repo = Repository.objects.filter(
            repoid=self.repo1.repoid
        ).with_latest_commit_totals_before(datetime.now().isoformat(), None)[0]
        assert repo.latest_commit_totals == totals

    def test_with_latest_coverage_change(self):
        CommitFactory(totals={"c": 99}, repository=self.repo1)
        CommitFactory(totals={"c": 98}, repository=self.repo1)
        assert (
            Repository.objects.filter(repoid=self.repo1.repoid)
            .with_latest_commit_totals_before(timezone.now().isoformat(), None, True)
            .with_latest_coverage_change()[0]
            .latest_coverage_change
            == -1
        )

    def test_get_or_create_from_github_repo_data(self):
        owner = OwnerFactory()

        with self.subTest("doesnt crash when fork but no parent"):
            repo_data = {
                "id": 45,
                "default_branch": "main",
                "private": True,
                "name": "test",
                "fork": True,
            }

            repo, created = Repository.objects.get_or_create_from_git_repo(
                repo_data, owner
            )
            assert created
            assert repo.service_id == 45
            assert repo.branch == "main"
            assert repo.private
            assert repo.name == "test"

    def test_viewable_repos(self):
        private_repo = RepositoryFactory(private=True)
        public_repo = RepositoryFactory(private=False)
        deleted_repo = RepositoryFactory(deleted=True)

        with self.subTest("when owner permission is none doesnt crash"):
            owner = OwnerFactory(permission=None)
            owned_repo = RepositoryFactory(author=owner)

            repos = Repository.objects.viewable_repos(owner)
            assert repos.count() == 2

            repoids = repos.values_list("repoid", flat=True)
            assert public_repo.repoid in repoids
            assert owned_repo.repoid in repoids
            assert deleted_repo.repoid not in repoids

        with self.subTest("when repository do not have a name doesnt return it"):
            owner = OwnerFactory(permission=None)
            RepositoryFactory(author=owner, name=None)
            RepositoryFactory(author=owner, name=None)
            RepositoryFactory(author=owner, name=None)

            repos = Repository.objects.viewable_repos(owner)
            assert repos.count() == 1
            # only public repo created above
            repoids = repos.values_list("repoid", flat=True)
            assert public_repo.repoid in repoids
            assert deleted_repo.repoid not in repoids

        with self.subTest("when owner permission is not none, returns repos"):
            owner = OwnerFactory(permission=[private_repo.repoid])
            owned_repo = RepositoryFactory(author=owner)

            repos = Repository.objects.viewable_repos(owner)
            assert repos.count() == 3

            repoids = repos.values_list("repoid", flat=True)
            assert public_repo.repoid in repoids
            assert owned_repo.repoid in repoids
            assert private_repo.repoid in repoids
            assert deleted_repo.repoid not in repoids

        with self.subTest("when user not authed, returns only public"):
            repos = Repository.objects.viewable_repos(None)
            assert repos.count() == 1

            repoids = repos.values_list("repoid", flat=True)
            assert public_repo.repoid in repoids
            assert deleted_repo.repoid not in repoids

        with self.subTest("when repository is deleted, don't return it"):
            owner = OwnerFactory()
            deleted_owned_repo = RepositoryFactory(author=owner, deleted=True)

            repos = Repository.objects.viewable_repos(owner)
            assert public_repo.repoid in repoids
            assert deleted_repo not in repoids
            assert deleted_owned_repo not in repoids
