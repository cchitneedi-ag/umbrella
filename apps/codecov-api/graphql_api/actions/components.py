from collections.abc import Iterable, Mapping
from datetime import datetime

from django.db.models import QuerySet

from core.models import Repository
from graphql_api.actions.measurements import (
    measurements_by_ids,
    measurements_last_uploaded_by_ids,
)
from timeseries.models import Interval, MeasurementName


def component_measurements(
    repository: Repository,
    component_ids: Iterable[str],
    interval: Interval,
    after: datetime,
    before: datetime,
    branch: str | None = None,
) -> Mapping[int, Iterable[dict]]:
    return measurements_by_ids(
        repository=repository,
        measurable_name=MeasurementName.COMPONENT_COVERAGE.value,
        measurable_ids=component_ids,
        interval=interval,
        after=after,
        before=before,
        branch=branch,
    )


def component_measurements_last_uploaded(
    owner_id: int,
    repo_id: int,
    measurable_ids: str,
    branch: str | None = None,
) -> QuerySet:
    return measurements_last_uploaded_by_ids(
        owner_id=owner_id,
        repo_id=repo_id,
        measurable_name=MeasurementName.COMPONENT_COVERAGE.value,
        measurable_ids=measurable_ids,
        branch=branch,
    )
