from datetime import datetime
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from freezegun import freeze_time

from codecov.commands.exceptions import ValidationError
from codecov_auth.tests.factories import OwnerFactory
from core.tests.factories import CommitFactory, RepositoryFactory
from timeseries.models import Dataset, MeasurementName

from ..activate_component_measurements import ActivateComponentMeasurementsInteractor


@pytest.mark.skipif(
    not settings.TIMESERIES_ENABLED, reason="requires timeseries data storage"
)
class ActivateComponentMeasurementsInteractorTest(TransactionTestCase):
    databases = {"default", "timeseries"}

    def setUp(self):
        self.org = OwnerFactory(username="test-org")
        self.repo = RepositoryFactory(author=self.org, name="test-repo", active=True)
        self.user = OwnerFactory(permission=[self.repo.pk])

    @async_to_sync
    def execute(self, user, repo_name=None):
        current_user = user or AnonymousUser()
        return ActivateComponentMeasurementsInteractor(current_user, "github").execute(
            repo_name=repo_name or "test-repo",
            owner_name="test-org",
        )

    def test_repo_not_found(self):
        with pytest.raises(ValidationError):
            self.execute(user=self.user, repo_name="wrong")

    @override_settings(TIMESERIES_ENABLED=False)
    def test_timeseries_not_enabled(self):
        with pytest.raises(ValidationError):
            self.execute(user=self.user)

    @patch("services.task.TaskService.backfill_dataset")
    def test_creates_dataset(self, backfill_dataset):
        assert not Dataset.objects.filter(
            name=MeasurementName.COMPONENT_COVERAGE.value,
            repository_id=self.repo.pk,
        ).exists()

        self.execute(user=self.user)

        assert Dataset.objects.filter(
            name=MeasurementName.COMPONENT_COVERAGE.value,
            repository_id=self.repo.pk,
        ).exists()

    @patch("services.task.TaskService.backfill_dataset")
    @freeze_time("2022-01-01T00:00:00")
    def test_triggers_task(self, backfill_dataset):
        CommitFactory(repository=self.repo, timestamp=datetime(2000, 1, 1, 1, 1, 1))
        CommitFactory(repository=self.repo, timestamp=datetime(2021, 12, 31, 1, 1, 1))
        self.execute(user=self.user)
        dataset = Dataset.objects.filter(
            name=MeasurementName.COMPONENT_COVERAGE.value,
            repository_id=self.repo.pk,
        ).first()
        backfill_dataset.assert_called_once_with(
            dataset,
            start_date=timezone.datetime(2000, 1, 1),
            end_date=timezone.datetime(2022, 1, 1),
        )

    @patch("services.task.TaskService.backfill_dataset")
    def test_no_commits(self, backfill_dataset):
        self.execute(user=self.user)
        assert backfill_dataset.call_count == 0
