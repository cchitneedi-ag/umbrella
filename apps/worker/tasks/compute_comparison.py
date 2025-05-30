import logging
from typing import Literal, TypedDict

import orjson
import sentry_sdk
from asgiref.sync import async_to_sync
from celery import group

from app import celery_app
from database.enums import CompareCommitError, CompareCommitState
from database.models import CompareCommit, CompareComponent, CompareFlag
from database.models.reports import RepositoryFlag
from helpers.comparison import minimal_totals
from helpers.github_installation import get_installation_name_for_owner_for_task
from rollouts import PARALLEL_COMPONENT_COMPARISON
from services.comparison import ComparisonProxy, FilteredComparison
from services.comparison_utils import get_comparison_proxy
from services.report import ReportService
from services.yaml import get_current_yaml, get_repo_yaml
from shared.api_archive.archive import ArchiveService
from shared.celery_config import compute_comparison_task_name
from shared.components import Component
from shared.helpers.flag import Flag
from shared.torngit.exceptions import TorngitRateLimitError
from shared.yaml import UserYaml
from tasks.base import BaseCodecovTask
from tasks.compute_component_comparison import compute_component_comparison_task

log = logging.getLogger(__name__)


ComputeComparisonTaskErrors = (
    Literal["missing_head_report"]
    | Literal["missing_base_report"]
    | Literal["torngit_rate_limit"]
)


class ComputeComparisonTaskReturn(TypedDict):
    success: bool
    error: ComputeComparisonTaskErrors | None


class ComputeComparisonTask(BaseCodecovTask, name=compute_comparison_task_name):
    def run_impl(
        self, db_session, comparison_id, *args, **kwargs
    ) -> ComputeComparisonTaskReturn:
        comparison: CompareCommit = db_session.query(CompareCommit).get(comparison_id)
        repo = comparison.compare_commit.repository
        log_extra = {
            "comparison_id": comparison_id,
            "repoid": repo.repoid,
            "commit": comparison.compare_commit.commitid,
        }
        log.info("Computing comparison", extra=log_extra)
        current_yaml = get_repo_yaml(repo)
        installation_name_to_use = get_installation_name_for_owner_for_task(
            self.name, repo.owner
        )
        report_service = ReportService(
            current_yaml, gh_app_installation_name=installation_name_to_use
        )

        comparison_proxy = get_comparison_proxy(comparison, report_service)
        if not comparison_proxy.has_head_report():
            comparison.error = CompareCommitError.missing_head_report.value
            comparison.state = CompareCommitState.error.value
            log.warning("Comparison doesn't have HEAD report", extra=log_extra)
            return {"successful": False, "error": "missing_head_report"}

        # At this point we can calculate the patch coverage
        # Because we have a HEAD report and a base commit to get the diff from
        patch_totals = comparison_proxy.get_patch_totals()
        comparison.patch_totals = minimal_totals(patch_totals)
        db_session.commit()

        if not comparison_proxy.has_project_coverage_base_report():
            comparison.error = CompareCommitError.missing_base_report.value
            log.warning(
                "Comparison doesn't have BASE report",
                extra={"base_commit": comparison.base_commit.commitid, **log_extra},
            )
            comparison.state = CompareCommitState.error.value
            return {"successful": False, "error": "missing_base_report"}
        else:
            comparison.error = None

        try:
            impacted_files = comparison_proxy.get_impacted_files()
        except TorngitRateLimitError:
            log.warning(
                "Unable to compute comparison due to rate limit error",
                extra={
                    "comparison_id": comparison_id,
                    "repoid": comparison.compare_commit.repoid,
                },
            )
            comparison.state = CompareCommitState.error.value
            return {"successful": False, "error": "torngit_rate_limit"}

        log.info("Files impact calculated", extra=log_extra)
        self.store_results(comparison, impacted_files)

        comparison.state = CompareCommitState.processed.value
        log.info("Computing comparison successful", extra=log_extra)
        db_session.commit()

        self.compute_flag_comparison(db_session, comparison, comparison_proxy)
        db_session.commit()
        self.compute_component_comparisons(db_session, comparison, comparison_proxy)
        db_session.commit()

        return {"successful": True}

    def compute_flag_comparison(self, db_session, comparison, comparison_proxy):
        log_extra = {"comparison_id": comparison.id}
        log.info("Computing flag comparisons", extra=log_extra)
        head_report_flags = comparison_proxy.comparison.head.report.flags
        if not head_report_flags:
            log.info("Head report does not have any flags", extra=log_extra)
            return
        self.create_or_update_flag_comparisons(
            db_session,
            head_report_flags,
            comparison,
            comparison_proxy,
        )

    @sentry_sdk.trace
    def create_or_update_flag_comparisons(
        self,
        db_session,
        head_report_flags: dict[str, Flag],
        comparison: CompareCommit,
        comparison_proxy: ComparisonProxy,
    ):
        repository_id = comparison.compare_commit.repository.repoid
        for flag_name in head_report_flags.keys():
            totals = self.get_flag_comparison_totals(flag_name, comparison_proxy)
            repositoryflag = (
                db_session.query(RepositoryFlag)
                .filter_by(
                    flag_name=flag_name,
                    repository_id=repository_id,
                )
                .first()
            )
            if not repositoryflag:
                log.warning(
                    "Repository flag not found for flag. Created repository flag.",
                    extra={"repoid": repository_id, "flag_name": flag_name},
                )
                repositoryflag = RepositoryFlag(
                    repository_id=repository_id,
                    flag_name=flag_name,
                )
                db_session.add(repositoryflag)
                db_session.flush()

            flag_comparison_entry = (
                db_session.query(CompareFlag)
                .filter_by(
                    commit_comparison_id=comparison.id,
                    repositoryflag_id=repositoryflag.id,
                )
                .first()
            )

            if not flag_comparison_entry:
                log.debug(
                    "No previous flag comparisons; adding flag comparisons",
                    extra={"repoid": repository_id},
                )
                self.store_flag_comparison(
                    db_session, comparison, repositoryflag, totals
                )
            else:
                log.debug(
                    "Updating totals for existing flag comparison entry",
                    extra={"repoid": repository_id},
                )
                flag_comparison_entry.head_totals = totals["head_totals"]
                flag_comparison_entry.base_totals = totals["base_totals"]
                flag_comparison_entry.patch_totals = totals["patch_totals"]
        log.info(
            "Flag comparisons stored successfully",
            extra={"number_stored": len(head_report_flags)},
        )

    def get_flag_comparison_totals(
        self,
        flag_name: str,
        comparison_proxy: ComparisonProxy,
    ):
        flag_head_report = comparison_proxy.comparison.head.report.flags.get(flag_name)
        flag_base_report = (
            comparison_proxy.comparison.project_coverage_base.report.flags.get(
                flag_name
            )
        )
        head_totals = None if not flag_head_report else flag_head_report.totals.asdict()
        base_totals = None if not flag_base_report else flag_base_report.totals.asdict()
        totals = {
            "head_totals": head_totals,
            "base_totals": base_totals,
            "patch_totals": None,
        }
        diff = comparison_proxy.get_diff()
        if diff:
            patch_totals = flag_head_report.apply_diff(diff)
            if patch_totals:
                totals["patch_totals"] = patch_totals.asdict()
        return totals

    def store_flag_comparison(
        self,
        db_session,
        comparison: CompareCommit,
        repositoryflag: RepositoryFlag,
        totals,
    ):
        flag_comparison = CompareFlag(
            commit_comparison=comparison,
            repositoryflag=repositoryflag,
            patch_totals=totals["patch_totals"],
            head_totals=totals["head_totals"],
            base_totals=totals["base_totals"],
        )
        db_session.add(flag_comparison)
        db_session.flush()

    @sentry_sdk.trace
    def compute_component_comparisons(
        self, db_session, comparison: CompareCommit, comparison_proxy: ComparisonProxy
    ):
        head_commit = comparison_proxy.comparison.head.commit
        yaml: UserYaml = async_to_sync(get_current_yaml)(
            head_commit, comparison_proxy.repository_service
        )
        components = yaml.get_components()
        log.info(
            "Computing component comparisons",
            extra={
                "comparison_id": comparison.id,
                "component_count": len(components),
            },
        )
        if PARALLEL_COMPONENT_COMPARISON.check_value(
            comparison.compare_commit.repoid, default=False
        ):
            self.parallel_compute_component_comparison(comparison.id, components)
        else:
            for component in components:
                self.compute_component_comparison(
                    db_session, comparison, comparison_proxy, component
                )

    @sentry_sdk.trace
    def parallel_compute_component_comparison(
        self,
        comparison_id: int,
        components: list[Component],
    ):
        task_group = group(
            [
                compute_component_comparison_task.s(
                    comparison_id, component.component_id
                )
                for component in components
            ]
        )
        task_group.apply_async()

    def compute_component_comparison(
        self,
        db_session,
        comparison: CompareCommit,
        comparison_proxy: ComparisonProxy,
        component: Component,
    ):
        component_comparison = (
            db_session.query(CompareComponent)
            .filter_by(
                commit_comparison_id=comparison.id,
                component_id=component.component_id,
            )
            .first()
        )
        if not component_comparison:
            component_comparison = CompareComponent(
                commit_comparison=comparison,
                component_id=component.component_id,
            )

        # filter comparison by component
        head_report = comparison_proxy.comparison.head.report
        flags = component.get_matching_flags(head_report.flags.keys())
        filtered: FilteredComparison = comparison_proxy.get_filtered_comparison(
            flags=flags, path_patterns=component.paths
        )

        # component comparison totals
        component_comparison.base_totals = (
            filtered.project_coverage_base.report.totals.asdict()
        )
        component_comparison.head_totals = filtered.head.report.totals.asdict()
        diff = comparison_proxy.get_diff()
        if diff:
            patch_totals = filtered.head.report.apply_diff(diff)
            if patch_totals:
                component_comparison.patch_totals = patch_totals.asdict()

        db_session.add(component_comparison)
        db_session.flush()

    @sentry_sdk.trace
    def store_results(self, comparison: CompareCommit, impacted_files):
        repository = comparison.compare_commit.repository
        storage_service = ArchiveService(repository)

        path = (
            f"v4/repos/{storage_service.storage_hash}/comparisons/{comparison.id}.json"
        )
        storage_service.write_file(path, orjson.dumps(impacted_files))

        comparison.report_storage_path = path


RegisteredComputeComparisonTask = celery_app.register_task(ComputeComparisonTask())
compute_comparison_task = celery_app.tasks[RegisteredComputeComparisonTask.name]
