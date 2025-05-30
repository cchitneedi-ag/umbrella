import random
from datetime import UTC, datetime, timedelta

from django.db.models.query import QuerySet

from services.cleanup.cleanup import cleanup_queryset
from services.cleanup.utils import CleanupContext
from shared.django_apps.reports.models import ReportSession as Upload

UPLOAD_CHUNKSIZE = 5_000


def cleanup_old_uploads(context: CleanupContext):
    queries = create_upload_cleanup_queries()
    random.shuffle(queries)

    for query in queries:
        query = query.values_list("pk", flat=True)
        while True:
            upload_ids = list(query[:UPLOAD_CHUNKSIZE])
            if len(upload_ids) == 0:
                break

            uploads_query = Upload.objects.filter(pk__in=upload_ids)
            cleanup_queryset(uploads_query, context)


UPLOAD_RETENTION_PERIOD = 150
MONTH_SLOTS = 20


def create_upload_cleanup_queries() -> list[QuerySet]:
    """
    This returns a list of `Upload` querysets, each targetting a subset of to-delete data.

    As the `Upload` table is one of our biggest tables, running an (almost)
    unbounded `DELETE` query would certainly cause problems.

    Fortunately though, the (production) table has an index on `created_at`,
    so queries targetting a range on that field should be fairly quick, and we
    can use that to devide up the deletion workload onto more manageable chunks.

    We are targetting 180-day chunks, going back ~10 years.
    """
    latest_timestamp = datetime.now(UTC) - timedelta(days=UPLOAD_RETENTION_PERIOD)
    timestamps = [latest_timestamp]
    for _ in range(MONTH_SLOTS):
        timestamps.append(timestamps[-1] - timedelta(days=180))
    timestamps.reverse()

    begin_timestamp = None
    queries: list[QuerySet] = []
    for timestamp in timestamps:
        query = Upload.objects
        if begin_timestamp:
            query = query.filter(created_at__gte=begin_timestamp)
        query = query.filter(created_at__lt=timestamp)
        queries.append(query)

        begin_timestamp = timestamp

    return queries
