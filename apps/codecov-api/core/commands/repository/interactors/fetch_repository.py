import sentry_sdk
from asgiref.sync import sync_to_async

from codecov.commands.base import BaseInteractor
from shared.django_apps.codecov_auth.models import Owner
from shared.django_apps.core.models import Repository


class FetchRepositoryInteractor(BaseInteractor):
    @sync_to_async
    @sentry_sdk.trace
    def execute(
        self,
        owner: Owner,
        name: str,
        okta_authenticated_accounts: list[int],
        exclude_okta_enforced_repos: bool = True,
        needs_coverage: bool = True,
        needs_commits: bool = True,
    ) -> Repository | None:
        queryset = Repository.objects.viewable_repos(self.current_owner)
        if exclude_okta_enforced_repos:
            queryset = queryset.exclude_accounts_enforced_okta(
                okta_authenticated_accounts
            )

        if needs_coverage:
            queryset = queryset.with_recent_coverage()
        if needs_commits:
            queryset = queryset.with_oldest_commit_at()

        repo = queryset.filter(author=owner, name=name).select_related("author").first()

        return repo
