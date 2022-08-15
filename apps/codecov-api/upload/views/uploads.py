import logging

from django.http import HttpRequest, HttpResponseNotAllowed
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import AllowAny

from core.models import Commit, Repository
from reports.models import CommitReport
from services.archive import ArchiveService, MinioEndpoints
from upload.serializers import UploadSerializer

log = logging.getLogger(__name__)


class UploadViews(ListCreateAPIView):
    serializer_class = UploadSerializer
    permission_classes = [
        # TODO: implement the correct permissions
        AllowAny,
    ]

    def perform_create(self, serializer):
        repository = self.get_repo()
        commit = self.get_commit(repository)
        report = self.get_report(commit)
        archive_service = ArchiveService(repository)
        path = MinioEndpoints.raw.get_path(
            version="v4",
            date=timezone.now().strftime("%Y-%m-%d"),
            repo_hash=archive_service.storage_hash,
            commit_sha=commit.commitid,
            reportid=report.external_id,
        )
        instance = serializer.save(storage_path=path, report_id=report.id)
        return instance

    def list(self, request: HttpRequest, repo: str, commit_sha: str, reportid: str):
        return HttpResponseNotAllowed(permitted_methods=["POST"])

    def get_repo(self) -> Repository:
        # TODO this is not final - how is getting the repo is still in discuss
        repoid = self.kwargs["repo"]
        try:
            repository = Repository.objects.get(name=repoid)
            return repository
        except Repository.DoesNotExist:
            raise ValidationError(detail="Repository not found")

    def get_commit(self, repo: Repository) -> Commit:
        commit_sha = self.kwargs["commit_sha"]
        try:
            commit = Commit.objects.get(
                commitid=commit_sha, repository__repoid=repo.repoid
            )
            return commit
        except Commit.DoesNotExist:
            raise ValidationError(
                detail="Commit SHA not found",
            )

    def get_report(self, commit: Commit) -> CommitReport:
        report_id = self.kwargs["reportid"]
        try:
            report = CommitReport.objects.get(
                external_id__exact=report_id, commit__commitid=commit.commitid
            )
            return report
        except CommitReport.DoesNotExist:
            raise ValidationError(
                detail="Report not found",
            )
