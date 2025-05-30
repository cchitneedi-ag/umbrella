import logging

from asgiref.sync import async_to_sync
from sqlalchemy.orm.session import Session

from app import celery_app
from database.models.core import Repository
from helpers.clock import get_utc_now
from helpers.github_installation import get_installation_name_for_owner_for_task
from services.repository import get_repo_provider_service
from shared.celery_config import sync_repo_languages_task_name
from shared.torngit.exceptions import TorngitError
from tasks.base import BaseCodecovTask

log = logging.getLogger(__name__)

BUNDLE_ANALYSIS_LANGUAGES = ["javascript", "typescript"]

# We sync on repos that don't have the desired BA languages every 7 days
REPOSITORY_LANGUAGE_SYNC_THRESHOLD = 7


class SyncRepoLanguagesTask(BaseCodecovTask, name=sync_repo_languages_task_name):
    def run_impl(
        self, db_session: Session, repoid: int, manual_trigger=False, *args, **kwargs
    ):
        repository = db_session.query(Repository).get(repoid)
        if repository is None:
            return {"successful": False, "error": "no_repo_in_db"}

        now = get_utc_now()
        days_since_sync = REPOSITORY_LANGUAGE_SYNC_THRESHOLD

        if repository.languages_last_updated:
            days_since_sync = abs(
                (now.replace(tzinfo=None) - repository.languages_last_updated).days
            )

        desired_languages_intersection = set(BUNDLE_ANALYSIS_LANGUAGES).intersection(
            repository.languages or {}
        )

        should_sync_languages = (
            days_since_sync >= REPOSITORY_LANGUAGE_SYNC_THRESHOLD
            and len(desired_languages_intersection) == 0
        ) or manual_trigger

        if not should_sync_languages:
            return {"successful": True, "synced": False}

        log_extra = {
            "owner_id": repository.ownerid or "",
            "repository_id": repository.repoid,
        }
        log.info("Syncing repository languages", extra=log_extra)

        installation_name_to_use = get_installation_name_for_owner_for_task(
            self.name, repository.owner
        )
        repository_service = get_repo_provider_service(
            repository, installation_name_to_use=installation_name_to_use
        )
        if not repository_service:
            log.warning(
                "Failed to create repository_service. Exiting",
                extra=log_extra,
            )
            return {"successful": False, "error": "no_repo_service"}

        is_bitbucket_call = (
            repository.owner.service == "bitbucket"
            or repository.owner.service == "bitbucket_server"
        )
        try:
            if is_bitbucket_call:
                languages = async_to_sync(repository_service.get_repo_languages)(
                    token=None, language=repository.language
                )
            else:
                languages = async_to_sync(repository_service.get_repo_languages)()
            repository.languages = languages
            repository.languages_last_updated = now
        except TorngitError:
            log.warning(
                "Unable to find languages for this repository",
                extra={"repoid": repoid},
            )
            return {"successful": False, "error": "no_repo_in_provider"}

        db_session.flush()
        return {"successful": True}


RegisteredSyncRepoLanguagesTask = celery_app.register_task(SyncRepoLanguagesTask())
sync_repo_language_task = celery_app.tasks[RegisteredSyncRepoLanguagesTask.name]
