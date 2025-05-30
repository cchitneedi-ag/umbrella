from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import TestCase
from freezegun import freeze_time
from freezegun.api import FakeDatetime

from shared.django_apps.core.tests.factories import (
    CommitFactory,
    OwnerFactory,
    RepositoryFactory,
)
from shared.django_apps.timeseries.tests.factories import (
    DatasetFactory,
    MeasurementFactory,
)
from timeseries.helpers import (
    coverage_measurements,
    fill_sparse_measurements,
    owner_coverage_measurements_with_fallback,
    refresh_measurement_summaries,
    repository_coverage_measurements_with_fallback,
)
from timeseries.models import Dataset, Interval, MeasurementName


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class RefreshMeasurementSummariesTest(TestCase):
    databases = {"timeseries"}

    @patch("django.db.backends.utils.CursorWrapper.execute")
    def test_refresh_measurement_summaries(self, execute):
        refresh_measurement_summaries(
            start_date=datetime(2022, 1, 1, 0, 0, 0),
            end_date=datetime(2022, 1, 2, 0, 0, 0),
        )

        assert execute.call_count == 3
        sql_statements = [call[0][0] for call in execute.call_args_list]
        assert sql_statements == [
            "CALL refresh_continuous_aggregate('timeseries_measurement_summary_1day', '2022-01-01T00:00:00', '2022-01-02T00:00:00')",
            "CALL refresh_continuous_aggregate('timeseries_measurement_summary_7day', '2022-01-01T00:00:00', '2022-01-02T00:00:00')",
            "CALL refresh_continuous_aggregate('timeseries_measurement_summary_30day', '2022-01-01T00:00:00', '2022-01-02T00:00:00')",
        ]


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class RepositoryCoverageMeasurementsTest(TestCase):
    databases = {"default", "timeseries"}

    def setUp(self):
        self.repo = RepositoryFactory()

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit4",
        )

    def test_coverage_measurements(self):
        res = coverage_measurements(
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 30, 0, 0, 0),
            end_date=datetime(2022, 1, 4, 0, 0, 0),
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            branch=self.repo.branch,
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class FillSparseMeasurementsTest(TestCase):
    databases = {"default", "timeseries"}

    def setUp(self):
        self.repo = RepositoryFactory()

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit4",
        )

    def test_fill_sparse_measurements(self):
        start_date = datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC)
        end_date = datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC)
        measurements = coverage_measurements(
            Interval.INTERVAL_1_DAY,
            start_date=start_date,
            end_date=end_date,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            branch="main",
        )
        assert fill_sparse_measurements(
            measurements, Interval.INTERVAL_1_DAY, start_date, end_date
        ) == [
            {
                "timestamp_bin": datetime(2021, 12, 31, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
            {
                "timestamp_bin": datetime(2022, 1, 3, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
        ]

    def test_fill_sparse_measurements_no_start_date(self):
        end_date = datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC)
        measurements = coverage_measurements(
            Interval.INTERVAL_1_DAY,
            end_date=end_date,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            branch="main",
        )
        assert fill_sparse_measurements(
            measurements, Interval.INTERVAL_1_DAY, start_date=None, end_date=end_date
        ) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
            {
                "timestamp_bin": datetime(2022, 1, 3, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
        ]

    @freeze_time("2022-01-03T00:00:00")
    def test_fill_sparse_measurements_no_end_date(self):
        start_date = datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC)
        measurements = coverage_measurements(
            Interval.INTERVAL_1_DAY,
            start_date=start_date,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            branch="main",
        )
        assert fill_sparse_measurements(
            measurements,
            Interval.INTERVAL_1_DAY,
            start_date=start_date,
        ) == [
            {
                "timestamp_bin": FakeDatetime(2021, 12, 31, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
            {
                "timestamp_bin": FakeDatetime(2022, 1, 3, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
        ]

    def test_fill_sparse_measurements_first_datapoint(self):
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2021, 12, 1, 1, 0, 0),
            value=80.0,
            branch="main",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2021, 12, 1, 1, 0, 0),
            value=90.0,
            branch="main",
        )

        start_date = datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC)
        end_date = datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC)
        measurements = coverage_measurements(
            Interval.INTERVAL_1_DAY,
            start_date=start_date,
            end_date=end_date,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            branch="main",
        )
        assert fill_sparse_measurements(
            measurements, Interval.INTERVAL_1_DAY, start_date, end_date
        ) == [
            {
                # this bin is carried forward from the last datapoint before `start_date`
                "timestamp_bin": datetime(2021, 12, 31, 0, 0, tzinfo=UTC),
                "avg": 85.0,
                "min": 80.0,
                "max": 90.0,
            },
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
            {
                "timestamp_bin": datetime(2022, 1, 3, 0, 0, tzinfo=UTC),
                "avg": None,
                "min": None,
                "max": None,
            },
        ]

    def test_fill_sparse_measurements_no_measurements(self):
        assert fill_sparse_measurements([], Interval.INTERVAL_1_DAY, None, None) == []


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class RepositoryCoverageMeasurementsWithFallbackTest(TestCase):
    databases = {"default", "timeseries"}

    def setUp(self):
        self.repo = RepositoryFactory()

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_backfilled_dataset(self, is_backfilled):
        is_backfilled.return_value = True

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit4",
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        res = repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_backfilled_dataset_no_start_end_dates(self, is_backfilled):
        is_backfilled.return_value = True

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2021, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo.author_id,
            repo_id=self.repo.pk,
            measurable_id=str(self.repo.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit4",
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        res = repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_unbackfilled_dataset(self, is_backfilled):
        is_backfilled.return_value = False

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        res = repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_unbackfilled_dataset_no_start_end_dates(self, is_backfilled):
        is_backfilled.return_value = False

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        res = repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.helpers.trigger_backfill")
    def test_no_dataset(self, trigger_backfill):
        CommitFactory(
            commitid="commit1",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )

        res = repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch (commit1, commit2)
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

        dataset = Dataset.objects.filter(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        ).first()
        assert dataset
        trigger_backfill.assert_called_once_with([dataset])

    @patch("timeseries.models.Dataset.is_backfilled")
    @patch("timeseries.helpers.trigger_backfill")
    @patch("timeseries.models.Dataset.objects.get_or_create")
    def test_backfill_trigger_on_dataset_creation(
        self, mock_get_or_create, mock_trigger_backfill, mock_is_backfilled
    ):
        mock_is_backfilled.return_value = False
        mock_get_or_create.return_value = (Dataset(), True)

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={"c": "80.00"},
        )

        # Invoke the logic
        repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )

        # Ensure get_or_create was called with the expected arguments
        mock_get_or_create.assert_called_once_with(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        # Ensure trigger_backfill was called when a new Dataset was created
        mock_trigger_backfill.assert_called_once_with(
            [mock_get_or_create.return_value[0]]
        )

    @patch("timeseries.models.Dataset.is_backfilled")
    @patch("timeseries.helpers.trigger_backfill")
    @patch("timeseries.models.Dataset.objects.get_or_create")
    def test_backfill_not_triggered_if_no_dataset_creation(
        self, mock_get_or_create, mock_trigger_backfill, mock_is_backfilled
    ):
        mock_is_backfilled.return_value = False
        mock_get_or_create.return_value = (Dataset(), False)

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={"c": "80.00"},
        )

        repository_coverage_measurements_with_fallback(
            self.repo,
            Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )

        mock_get_or_create.assert_called_once_with(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo.pk,
        )

        mock_trigger_backfill.assert_not_called()


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class OwnerCoverageMeasurementsWithFallbackTest(TestCase):
    databases = {"default", "timeseries"}

    def setUp(self):
        self.owner = OwnerFactory()
        self.repo1 = RepositoryFactory(author=self.owner)
        self.repo2 = RepositoryFactory(author=self.owner)

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_backfilled_datasets(self, is_backfilled):
        is_backfilled.return_value = True

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo1.author_id,
            repo_id=self.repo1.pk,
            measurable_id=str(self.repo1.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo1.author_id,
            repo_id=self.repo1.pk,
            measurable_id=str(self.repo1.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo1.author_id,
            repo_id=self.repo1.pk,
            measurable_id=str(self.repo1.pk),
            timestamp=datetime(2022, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo1.author_id,
            repo_id=self.repo1.pk,
            measurable_id=str(self.repo1.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit4",
        )

        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo2.author_id,
            repo_id=self.repo2.pk,
            measurable_id=str(self.repo2.pk),
            timestamp=datetime(2022, 1, 1, 1, 0, 0),
            value=80.0,
            branch="main",
            commit_sha="commit1",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo2.author_id,
            repo_id=self.repo2.pk,
            measurable_id=str(self.repo2.pk),
            timestamp=datetime(2022, 1, 1, 2, 0, 0),
            value=85.0,
            branch="main",
            commit_sha="commit2",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo2.author_id,
            repo_id=self.repo2.pk,
            measurable_id=str(self.repo2.pk),
            timestamp=datetime(2022, 1, 1, 3, 0, 0),
            value=90.0,
            branch="other",
            commit_sha="commit3",
        )
        MeasurementFactory(
            name=MeasurementName.COVERAGE.value,
            owner_id=self.repo2.author_id,
            repo_id=self.repo2.pk,
            measurable_id=str(self.repo2.pk),
            timestamp=datetime(2022, 1, 2, 1, 0, 0),
            value=90.0,
            branch="main",
            commit_sha="commit4",
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo1.pk,
        )
        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo2.pk,
        )

        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk, self.repo2.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 85.0,
                "min": 80.0,
                "max": 90.0,
            },
        ]
        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 measurements on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.models.Dataset.is_backfilled")
    def test_unbackfilled_dataset(self, is_backfilled):
        is_backfilled.return_value = False

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo1.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo2.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "90.00",
            },
        )

        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo1.pk,
        )
        DatasetFactory(
            name=MeasurementName.COVERAGE.value,
            repository_id=self.repo2.pk,
        )

        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk, self.repo2.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 commits on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 commit (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 85.0,
                "min": 80.0,
                "max": 90.0,
            },
        ]
        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 commits on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 commit (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]

    @patch("timeseries.helpers.trigger_backfill")
    def test_no_dataset(self, trigger_backfill):
        CommitFactory(
            commitid="commit1",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo1.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo1.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )

        CommitFactory(
            commitid="commit1",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "80.00",
            },
        )
        CommitFactory(
            commitid="commit2",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 1, 2, 0, 0, 0, tzinfo=UTC),
            totals={"c": "85.00"},
        )
        CommitFactory(
            commitid="commit3",
            repository_id=self.repo2.pk,
            branch="other",
            timestamp=datetime(2022, 1, 1, 3, 0, 0, 0, tzinfo=UTC),
            totals={"c": "90.00"},
        )
        CommitFactory(
            commitid="commit4",
            repository_id=self.repo2.pk,
            branch="main",
            timestamp=datetime(2022, 1, 2, 1, 0, 0, 0, tzinfo=UTC),
            totals={
                "c": "90.00",
            },
        )

        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk, self.repo2.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 commits on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 85.0,
                "min": 80.0,
                "max": 90.0,
            },
        ]

        datasets = list(
            Dataset.objects.filter(
                name=MeasurementName.COVERAGE.value,
                repository_id__in=[self.repo1.pk, self.repo2.pk],
            )
        )
        assert len(datasets) == 2
        created_datasets = [
            (
                ds.repository_id,
                ds.name,
                ds.is_backfilled(),
            )
            for ds in datasets
        ]

        assert (
            self.repo1.pk,
            MeasurementName.COVERAGE.value,
            False,
        ) in created_datasets
        assert (
            self.repo2.pk,
            MeasurementName.COVERAGE.value,
            False,
        ) in created_datasets

        try:
            trigger_backfill.assert_called_once_with(datasets)
        except AssertionError:
            datasets.reverse()
            trigger_backfill.assert_called_once_with(datasets)

        res = owner_coverage_measurements_with_fallback(
            owner=self.owner,
            repo_ids=[self.repo1.pk],
            interval=Interval.INTERVAL_1_DAY,
            start_date=datetime(2021, 12, 31, 0, 0, 0, tzinfo=UTC),
            end_date=datetime(2022, 1, 3, 0, 0, 0, tzinfo=UTC),
        )
        assert list(res) == [
            {
                # aggregates over 2 commits on main branch
                "timestamp_bin": datetime(2022, 1, 1, 0, 0, 0, tzinfo=UTC),
                "avg": 82.5,
                "min": 80.0,
                "max": 85.0,
            },
            {
                # aggregates over 1 measurement (commit4)
                "timestamp_bin": datetime(2022, 1, 2, 0, 0, 0, tzinfo=UTC),
                "avg": 80.0,
                "min": 80.0,
                "max": 80.0,
            },
        ]
