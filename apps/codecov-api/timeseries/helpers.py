import math
from collections.abc import Iterable
from datetime import datetime, timedelta

import sentry_sdk
from django.conf import settings
from django.db import connections
from django.db.models import (
    Avg,
    DateTimeField,
    DecimalField,
    F,
    FloatField,
    Func,
    Max,
    Min,
    QuerySet,
    Sum,
    Value,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone

from codecov_auth.models import Owner
from core.models import Commit, Repository
from services.task import TaskService
from timeseries.models import (
    Dataset,
    Interval,
    MeasurementName,
    MeasurementSummary,
)

interval_deltas = {
    Interval.INTERVAL_1_DAY: timedelta(days=1),
    Interval.INTERVAL_7_DAY: timedelta(days=7),
    Interval.INTERVAL_30_DAY: timedelta(days=30),
}


@sentry_sdk.trace
def refresh_measurement_summaries(start_date: datetime, end_date: datetime) -> None:
    """
    Refresh the measurement summaries for the given time range.
    This calls a TimescaleDB provided SQL function for each of the continuous aggregates
    to refresh the aggregate data in the provided time range.
    """
    continuous_aggregates = [
        "timeseries_measurement_summary_1day",
        "timeseries_measurement_summary_7day",
        "timeseries_measurement_summary_30day",
    ]
    with connections["timeseries"].cursor() as cursor:
        for cagg in continuous_aggregates:
            sql = f"CALL refresh_continuous_aggregate('{cagg}', '{start_date.isoformat()}', '{end_date.isoformat()}')"
            cursor.execute(sql)


@sentry_sdk.trace
def aggregate_measurements(
    queryset: QuerySet, group_by: Iterable[str] = None
) -> QuerySet:
    """
    The given queryset is a set of measurement summaries.  These are already
    pre-aggregated by (timestamp, owner_id, repo_id, measurable_id, branch) via TimescaleDB's
    continuous aggregates.  If we want to further aggregate over any of those columns
    then we need to perform additional aggregation in SQL.  That is what this function
    does to the given queryset.
    """
    if not group_by:
        group_by = ["timestamp_bin"]

    return (
        queryset.values(*group_by)
        .annotate(
            min=Min("value_min"),
            max=Max("value_max"),
            avg=Cast(
                Sum(F("value_avg") * F("value_count")) / Sum(F("value_count")),
                # this is equivalent to Postgres' numeric(1000, 5) type
                # 1000 is the max precision
                # (used to avoid floating point error)
                DecimalField(max_digits=1000, decimal_places=5),
            ),
        )
        .order_by("timestamp_bin")
    )


def _filter_repos(
    queryset: QuerySet, repos: list[Repository] | None, column_name: str = "repo_id"
) -> QuerySet:
    """
    Filter the given generic queryset by a set of (repoid, branch) tuples.
    """
    if repos:
        queryset = queryset.extra(
            where=[f"({column_name}, branch) in %s"],
            params=[tuple((repo.repoid, repo.branch) for repo in repos)],
        )
    return queryset


@sentry_sdk.trace
def coverage_measurements(
    interval: Interval,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    repos: list[Repository] | None = None,
    **filters,
):
    timestamp_filters = {}
    if start_date is not None:
        timestamp_filters["timestamp_bin__gte"] = start_date
    if end_date is not None:
        timestamp_filters["timestamp_bin__lte"] = end_date

    queryset = (
        MeasurementSummary.agg_by(interval)
        .filter(name=MeasurementName.COVERAGE.value, **timestamp_filters)
        .filter(**filters)
    )

    queryset = _filter_repos(queryset, repos)

    if start_date:
        # The first measurement of the specified range (`start_date` through `end_date`)
        # may be missing the first datapoint.  In order for consumers of this API to have
        # usable data to show we can carry an older datapoint forward to the first time bin.
        # Including this older datapoint in the result set makes that possible.
        older = (
            MeasurementSummary.agg_by(interval)
            .filter(
                name=MeasurementName.COVERAGE.value,
                timestamp_bin__lt=start_date,
            )
            .filter(**filters)
        )
        older = _filter_repos(older, repos)
        older = aggregate_measurements(older).order_by("-timestamp_bin")[:1]

        return older.union(aggregate_measurements(queryset)).order_by("timestamp_bin")
    else:
        return aggregate_measurements(queryset).order_by("timestamp_bin")


def trigger_backfill(datasets: list[Dataset]):
    """
    Triggers a backfill for the full timespan of the dataset's repo's commits.
    """
    repo_ids = {d.repository_id for d in datasets}
    timeranges = (
        Commit.objects.filter(repository_id__in=repo_ids)
        .values_list("repository_id")
        .annotate(start_date=Min("timestamp"), end_date=Max("timestamp"))
    )

    timerange_by_repo = {
        repo_id: (start_date, end_date) for repo_id, start_date, end_date in timeranges
    }

    for dataset in datasets:
        if dataset.repository_id not in timerange_by_repo:
            continue  # there are no commits, and thus nothing to backfill
        start_date, end_date = timerange_by_repo[dataset.repository_id]
        TaskService().backfill_dataset(
            dataset, start_date=start_date, end_date=end_date
        )


def aligned_start_date(interval: Interval, date: datetime) -> datetime:
    """
    Finds the aligned start date for the given timedelta and date.
    TimescaleDB aligns time buckets starting on 2000-01-03 so this function will
    return the date of the start of the bin containing the given `date`.
    The return value will be <= the given date.
    """
    delta = interval_deltas[interval]

    # TimescaleDB aligns time buckets starting on 2000-01-03)
    aligning_date = datetime(2000, 1, 3, tzinfo=timezone.utc)

    # number of full intervals between aligning date and the given date
    intervals_before = math.floor((date - aligning_date) / delta)

    # starting date of time bucket that contains the given date
    return aligning_date + (intervals_before * delta)


@sentry_sdk.trace
def fill_sparse_measurements(
    measurements: Iterable[dict],
    interval: Interval,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> Iterable[dict]:
    """
    Fill in sparse array of measurements with values such that we
    have an entry for every interval within the requested time range.
    Those placeholder entries will have empty measurement values.
    """
    by_timestamp = {
        measurement["timestamp_bin"].replace(tzinfo=timezone.utc): measurement
        for measurement in measurements
    }
    timestamps = sorted(by_timestamp.keys())
    if len(timestamps) == 0:
        return []

    delta = interval_deltas[interval]

    if start_date is None:
        start_date = timestamps[0]
    start_date = aligned_start_date(interval, start_date)

    if end_date is None:
        end_date = timezone.now()

    intervals = []

    current_date = start_date
    while current_date <= end_date:
        if current_date in by_timestamp:
            intervals.append(by_timestamp[current_date])
        else:
            # interval not found
            intervals.append(
                {
                    "timestamp_bin": current_date,
                    "avg": None,
                    "min": None,
                    "max": None,
                }
            )
        current_date += delta

    if len(timestamps) > 0:
        oldest_date = timestamps[0]
        if (
            oldest_date <= start_date
            and len(intervals) > 0
            and intervals[0]["avg"] is None
        ):
            # we're missing the first datapoint but we can carry forward
            # and older measurement that was selected
            measurement = by_timestamp[oldest_date]
            intervals[0] = {
                **measurement,
                "timestamp_bin": start_date,
            }

    return intervals


@sentry_sdk.trace
def coverage_fallback_query(
    interval: Interval,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    repos: list[Repository] | None = None,
    **filters,
):
    """
    Query for coverage timeseries directly from the database
    """
    timestamp_filters = {}
    if start_date is not None:
        timestamp_filters["timestamp__gte"] = start_date
    if end_date is not None:
        timestamp_filters["timestamp__lte"] = end_date
    commits = Commit.objects.filter(**timestamp_filters).filter(**filters)
    commits = _filter_repos(commits, repos, column_name="repoid")
    commits = _commits_coverage(commits, interval)

    if start_date:
        # The first measurement of the specified range (`start_date` through `end_date`)
        # may be missing the first datapoint.  In order for consumers of this API to have
        # usable data to show we can carry an older datapoint forward to the first time bin.
        # Including this older datapoint in the result set makes that possible.
        older = Commit.objects.filter(
            timestamp__lt=start_date,
        ).filter(**filters)
        older = _filter_repos(older, repos, column_name="repoid")
        older = _commits_coverage(older, interval).order_by("-timestamp_bin")[:1]

        return older.union(commits).order_by("timestamp_bin")
    else:
        return commits.order_by("timestamp_bin")


def _commits_coverage(
    commits_queryset: QuerySet[Commit], interval: Interval
) -> QuerySet[Commit]:
    intervals = {
        Interval.INTERVAL_1_DAY: "1 day",
        Interval.INTERVAL_7_DAY: "7 days",
        Interval.INTERVAL_30_DAY: "30 days",
    }

    return (
        commits_queryset.annotate(
            timestamp_bin=Func(
                Value(intervals[interval]),
                F("timestamp"),
                Value("2000-01-03"),  # mimic how Timescale aligns bins
                function="date_bin",
                template="%(function)s(%(expressions)s) at time zone 'utc'",
                output_field=DateTimeField(),
            ),
            coverage=Cast(KeyTextTransform("c", "totals"), output_field=FloatField()),
        )
        .filter(coverage__isnull=False)
        .values("timestamp_bin")
        .annotate(
            min=Min("coverage"),
            max=Max("coverage"),
            avg=Avg("coverage"),
        )
        .order_by("timestamp_bin")
    )


@sentry_sdk.trace
def repository_coverage_measurements_with_fallback(
    repository: Repository,
    interval: Interval,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    branch: str = None,
):
    """
    Tries to return repository coverage measurements from Timescale.
    If those are not available then we trigger a backfill and return computed results
    directly from the primary database (much slower to query).
    """
    if settings.TIMESERIES_ENABLED:
        dataset = Dataset.objects.filter(
            name=MeasurementName.COVERAGE.value,
            repository_id=repository.pk,
        ).first()

        if dataset and dataset.is_backfilled():
            # timeseries data is ready
            return coverage_measurements(
                interval,
                start_date=start_date,
                end_date=end_date,
                owner_id=repository.author_id,
                repo_id=repository.pk,
                measurable_id=str(repository.pk),
                branch=branch or repository.branch,
            )

        if not dataset:
            # we need to backfill
            dataset, created = Dataset.objects.get_or_create(
                name=MeasurementName.COVERAGE.value,
                repository_id=repository.pk,
            )
            if created:
                trigger_backfill([dataset])

    # we're still backfilling or timeseries is disabled
    return coverage_fallback_query(
        interval,
        start_date=start_date,
        end_date=end_date,
        repository_id=repository.pk,
        branch=branch or repository.branch,
    )


@sentry_sdk.trace
def owner_coverage_measurements_with_fallback(
    owner: Owner,
    repo_ids: Iterable[str],
    interval: Interval,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    """
    Tries to return owner coverage measurements from Timescale.
    If those are not available then we trigger a backfill and return computed results
    directly from the primary database (much slower to query).
    """
    # we can't join across databases so we need to load all this into memory.
    # select just the needed columns to keep this manageable
    repos = Repository.objects.filter(repoid__in=repo_ids).only("repoid", "branch")

    if settings.TIMESERIES_ENABLED:
        datasets = Dataset.objects.filter(
            name=MeasurementName.COVERAGE.value,
            repository_id__in=repo_ids,
        )
        all_backfilled = len(datasets) == len(repo_ids) and all(
            dataset.is_backfilled() for dataset in datasets
        )

        if all_backfilled:
            # timeseries data is ready
            return coverage_measurements(
                interval,
                start_date=start_date,
                end_date=end_date,
                owner_id=owner.pk,
                repos=repos,
            )

        # we need to backfill some datasets
        dataset_repo_ids = {dataset.repository_id for dataset in datasets}
        missing_dataset_repo_ids = set(repo_ids) - dataset_repo_ids
        created_datasets = Dataset.objects.bulk_create(
            [
                Dataset(name=MeasurementName.COVERAGE.value, repository_id=repo_id)
                for repo_id in missing_dataset_repo_ids
            ]
        )
        trigger_backfill(created_datasets)

    # we're still backfilling or timeseries is disabled
    return coverage_fallback_query(
        interval,
        start_date=start_date,
        end_date=end_date,
        repos=repos,
    )
