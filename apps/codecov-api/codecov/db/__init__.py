import logging

from django.conf import settings
from django.db.models import Field, Lookup

log = logging.getLogger(__name__)


class DatabaseRouter:
    """
    A router to control all database operations on models across multiple databases.
    https://docs.djangoproject.com/en/4.0/topics/db/multi-db/#automatic-database-routing
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label == "timeseries":
            if settings.TIMESERIES_DATABASE_READ_REPLICA_ENABLED:
                return "timeseries_read"
            else:
                return "timeseries"
        else:
            if settings.DATABASE_READ_REPLICA_ENABLED:
                return "default_read"
            else:
                return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label == "timeseries":
            return "timeseries"
        else:
            return "default"

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if (
            db == "timeseries" or db == "timeseries_read"
        ) and not settings.TIMESERIES_ENABLED:
            log.warning("Skipping timeseries migration")
            return False
        if db == "default_read" or db == "timeseries_read":
            log.warning("Skipping migration of read-only database")
            return False
        if app_label == "timeseries":
            return db == "timeseries"
        else:
            return db == "default"

    def allow_relation(self, obj1, obj2, **hints):
        obj1_app = obj1._meta.app_label
        obj2_app = obj2._meta.app_label

        # cannot form relationship across default <-> timeseries dbs
        if obj1_app == "timeseries" and obj2_app != "timeseries":
            return False
        if obj1_app != "timeseries" and obj2_app == "timeseries":
            return False

        # otherwise we allow it
        return True


@Field.register_lookup
class IsNot(Lookup):
    lookup_name = "isnot"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = tuple(lhs_params) + tuple(rhs_params)
        return f"{lhs} is not {rhs}", params
