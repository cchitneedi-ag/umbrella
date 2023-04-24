from typing import List

from rest_framework import serializers

from api.internal.commit.serializers import CommitSerializer
from api.shared.commit.serializers import ReportTotalsSerializer
from services.comparison import Comparison, FileComparison


class TotalsComparisonSerializer(serializers.Serializer):
    base = ReportTotalsSerializer()
    head = ReportTotalsSerializer()
    patch = ReportTotalsSerializer(source="diff")


class LineComparisonSerializer(serializers.Serializer):
    value = serializers.CharField()
    number = serializers.JSONField()
    coverage = serializers.JSONField()
    is_diff = serializers.BooleanField()
    added = serializers.BooleanField()
    removed = serializers.BooleanField()
    sessions = serializers.IntegerField(source="hit_count")


class FileComparisonSerializer(serializers.Serializer):
    name = serializers.JSONField()
    totals = TotalsComparisonSerializer()
    has_diff = serializers.BooleanField()
    stats = serializers.JSONField()
    change_summary = serializers.JSONField()
    lines = LineComparisonSerializer(many=True)


class ComparisonSerializer(serializers.Serializer):
    base_commit = serializers.CharField(source="base_commit.commitid")
    head_commit = serializers.CharField(source="head_commit.commitid")
    totals = TotalsComparisonSerializer()
    commit_uploads = CommitSerializer(many=True, source="upload_commits")
    diff = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    untracked = serializers.SerializerMethodField()
    has_unmerged_base_commits = serializers.BooleanField()

    def get_untracked(self, comparison) -> List[str]:
        return [
            f
            for f, _ in comparison.git_comparison["diff"]["files"].items()
            if f not in (comparison.base_report or [])
            and f not in comparison.head_report
        ]

    def get_diff(self, comparison) -> dict:
        return {"git_commits": comparison.git_commits}

    def get_files(self, comparison: Comparison) -> List[dict]:
        return [
            FileComparisonSerializer(file).data
            for file in comparison.files
            if self._should_include_file(file)
        ]

    def _should_include_file(self, file: FileComparison):
        if "has_diff" in self.context:
            return self.context["has_diff"] == file.has_diff
        else:
            return True


class FlagComparisonSerializer(serializers.Serializer):
    name = serializers.CharField(source="flag_name")
    base_report_totals = serializers.SerializerMethodField()
    head_report_totals = ReportTotalsSerializer(source="head_report.totals")
    diff_totals = ReportTotalsSerializer()

    def get_base_report_totals(self, obj):
        if obj.base_report:
            return ReportTotalsSerializer(obj.base_report.totals).data
