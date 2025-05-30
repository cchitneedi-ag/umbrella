from datetime import datetime, timedelta

from asgiref.sync import sync_to_async

from codecov.commands.base import BaseInteractor
from services.task.task import TaskService
from shared.django_apps.core.models import Pull, Repository


class FetchPullRequestInteractor(BaseInteractor):
    def _should_sync_pull(self, pull: Pull | None) -> bool:
        return (
            pull is not None
            and pull.state == "open"
            and pull.updatestamp is not None
            and (datetime.now(tz=None) - pull.updatestamp) > timedelta(hours=1)
        )

    @sync_to_async
    def execute(self, repository: Repository, id: int) -> Pull:
        pull = repository.pull_requests.filter(pullid=id).first()
        if self._should_sync_pull(pull):
            TaskService().pulls_sync(repository.repoid, id)

        return pull
