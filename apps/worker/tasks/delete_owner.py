import logging

from celery.exceptions import SoftTimeLimitExceeded

from app import celery_app
from services.cleanup.owner import cleanup_owner
from services.cleanup.utils import CleanupSummary
from shared.celery_config import delete_owner_task_name
from tasks.base import BaseCodecovTask

log = logging.getLogger(__name__)


class DeleteOwnerTask(BaseCodecovTask, name=delete_owner_task_name):
    acks_late = True  # retry the task when the worker dies for whatever reason
    max_retries = None  # aka, no limit on retries

    def run_impl(self, _db_session, ownerid: int) -> CleanupSummary:
        try:
            return cleanup_owner(ownerid)
        except SoftTimeLimitExceeded:
            raise self.retry()


RegisteredDeleteOwnerTask = celery_app.register_task(DeleteOwnerTask())
delete_owner_task = celery_app.tasks[DeleteOwnerTask.name]
