from dataclasses import dataclass
from typing import TypedDict

from database.models import Commit
from services.repository import EnrichedPull
from shared.reports.readonly import ReadOnlyReport
from shared.yaml import UserYaml


@dataclass
class FullCommit:
    commit: Commit
    report: ReadOnlyReport


class ReportUploadedCount(TypedDict):
    flag: str
    base_count: int
    head_count: int


@dataclass
class Comparison:
    head: FullCommit

    # To see how a patch changes project coverage, we compare the branch head's
    # report against the base's report, or if the base isn't in our database,
    # the next-oldest commit that is. Be aware that this base commit may not be
    # the true base that, for example, a PR is based on.
    project_coverage_base: FullCommit

    # Computing patch coverage doesn't require an old report to compare against,
    # so doing the "next-oldest" adjustment described above is unnecessary and
    # makes the results less correct. All it requires is a head report and the
    # patch diff, and the original base's commit SHA is enough to get that.
    patch_coverage_base_commitid: str

    enriched_pull: EnrichedPull
    current_yaml: UserYaml | None = None

    # FIXME: The functions down below would not make sense given that we assume
    # a `FullCommit` and its `report` to always exist.
    # Which they don't, so these checks do make sense, contrary to declared types.
    # Similarly, we also expect an `EnrichedPull` to exist, which does not match
    # the reality.

    def has_project_coverage_base_report(self):
        return bool(
            self.project_coverage_base is not None
            and self.project_coverage_base.report is not None
        )

    def has_head_report(self):
        return bool(self.head is not None and self.head.report is not None)

    @property
    def pull(self):
        if self.enriched_pull is None:
            return None
        return self.enriched_pull.database_pull
