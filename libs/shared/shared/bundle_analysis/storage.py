import logging
import tempfile
from enum import Enum

import sentry_sdk

from shared.api_archive.archive import ArchiveService
from shared.bundle_analysis.report import BundleAnalysisReport
from shared.config import get_config
from shared.storage.exceptions import FileNotInStorageError, PutRequestRateLimitError

log = logging.getLogger(__name__)


def get_bucket_name() -> str:
    return get_config("bundle_analysis", "bucket_name", default="bundle-analysis")


class StoragePaths(Enum):
    bundle_report = "v1/repos/{repo_key}/{report_key}/bundle_report.sqlite"
    upload = "v1/uploads/{upload_key}.json"

    def path(self, **kwargs):
        return self.value.format(**kwargs)


class BundleAnalysisReportLoader:
    """
    Loads and saves `BundleAnalysisReport`s into the underlying storage service.
    Requires a `repo_key` that uniquely and permanently (i.e. maybe not the name/slug)
    that identifies a repo in the storage layer.
    """

    def __init__(self, repository):
        archive_service = ArchiveService(repository)

        self.repo_key = archive_service.storage_hash
        self.storage_service = archive_service.storage
        self.bucket_name = get_bucket_name()

    @sentry_sdk.trace
    def load(self, report_key: str) -> BundleAnalysisReport | None:
        """
        Loads the `BundleAnalysisReport` for the given report key from storage
        or returns `None` if no such report exists.
        """
        path = StoragePaths.bundle_report.path(
            repo_key=self.repo_key, report_key=report_key
        )
        _, db_path = tempfile.mkstemp(prefix="bundle_analysis_")

        with open(db_path, "w+b") as f:
            try:
                self.storage_service.read_file(self.bucket_name, path, file_obj=f)
            except FileNotInStorageError:
                return None
        return BundleAnalysisReport(db_path)

    @sentry_sdk.trace
    def save(self, report: BundleAnalysisReport, report_key: str):
        """
        Saves a `BundleAnalysisReport` for the given report key into storage.
        """
        storage_path = StoragePaths.bundle_report.path(
            repo_key=self.repo_key, report_key=report_key
        )
        try:
            with open(report.db_path, "rb") as f:
                self.storage_service.write_file(self.bucket_name, storage_path, f)
        except Exception as e:
            log.info(f"Bundle analysis GCS save file error: {e}")
            if "TooManyRequests" in str(e):
                raise PutRequestRateLimitError("GCS Rate Limit Error for Saving File")
            else:
                raise e
