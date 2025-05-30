import logging
import uuid
from decimal import Decimal
from functools import cached_property

from sqlalchemy import Column, ForeignKey, Table, UniqueConstraint, types
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship

from database.base import CodecovBaseModel, MixinBaseClass, MixinBaseClassNoExternalID
from database.models.core import Commit, CompareCommit, Repository
from helpers.clock import get_utc_now
from helpers.number import precise_round

log = logging.getLogger(__name__)


class RepositoryFlag(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_repositoryflag"
    repository_id = Column(types.Integer, ForeignKey("repos.repoid"))
    repository = relationship(Repository, backref=backref("flags"))
    flag_name = Column(types.String(1024), nullable=False)
    deleted = Column(types.Boolean, nullable=True)


class CommitReport(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_commitreport"
    commit_id = Column(types.BigInteger, ForeignKey("commits.id"))
    code = Column(types.String(100), nullable=True)
    report_type = Column(types.String(100), nullable=True)
    commit: Commit = relationship(
        "Commit",
        foreign_keys=[commit_id],
        back_populates="reports_list",
        cascade="all, delete",
    )
    totals = relationship(
        "ReportLevelTotals",
        back_populates="report",
        uselist=False,
        cascade="all, delete",
        passive_deletes=True,
    )
    uploads = relationship(
        "Upload", back_populates="report", cascade="all, delete", passive_deletes=True
    )
    test_result_totals = relationship(
        "TestResultReportTotals",
        back_populates="report",
        uselist=False,
        cascade="all, delete",
        passive_deletes=True,
    )


uploadflagmembership = Table(
    "reports_uploadflagmembership",
    CodecovBaseModel.metadata,
    Column("upload_id", types.BigInteger, ForeignKey("reports_upload.id")),
    Column("flag_id", types.BigInteger, ForeignKey("reports_repositoryflag.id")),
)


class Upload(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_upload"
    build_code = Column(types.Text)
    build_url = Column(types.Text)
    env = Column(postgresql.JSON)
    job_code = Column(types.Text)
    name = Column(types.String(100))
    provider = Column(types.String(50))
    report_id = Column(types.BigInteger, ForeignKey("reports_commitreport.id"))
    report: CommitReport = relationship(
        "CommitReport", foreign_keys=[report_id], back_populates="uploads"
    )
    state = Column(types.String(100), nullable=False)
    storage_path = Column(types.Text, nullable=False)
    order_number = Column(types.Integer)
    flags = relationship(RepositoryFlag, secondary=uploadflagmembership)
    totals = relationship(
        "UploadLevelTotals",
        back_populates="upload",
        uselist=False,
        cascade="all, delete",
        passive_deletes=True,
    )
    upload_extras = Column(postgresql.JSON, nullable=False)
    upload_type = Column(types.String(100), nullable=False)
    state_id = Column(types.Integer)
    upload_type_id = Column(types.Integer)

    @cached_property
    def flag_names(self) -> list[str]:
        return [f.flag_name for f in self.flags]


class UploadError(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_uploaderror"
    report_upload = relationship(Upload, backref="errors")
    upload_id = Column("upload_id", types.BigInteger, ForeignKey("reports_upload.id"))
    error_code = Column(types.String(100), nullable=False)
    error_params = Column(postgresql.JSON, default=dict)


class AbstractTotals(MixinBaseClass):
    branches = Column(types.Integer)
    coverage = Column(types.Numeric(precision=8, scale=5))
    hits = Column(types.Integer)
    lines = Column(types.Integer)
    methods = Column(types.Integer)
    misses = Column(types.Integer)
    partials = Column(types.Integer)
    files = Column(types.Integer)

    def update_from_totals(self, totals, precision=2, rounding="down"):
        self.branches = totals.branches
        if totals.coverage is not None:
            coverage: Decimal = Decimal(totals.coverage)
            self.coverage = precise_round(
                coverage, precision=precision, rounding=rounding
            )
        # Temporary until the table starts accepting NULLs
        else:
            self.coverage = 0
        self.hits = totals.hits
        self.lines = totals.lines
        self.methods = totals.methods
        self.misses = totals.misses
        self.partials = totals.partials
        self.files = totals.files

    class Meta:
        abstract = True


class ReportLevelTotals(CodecovBaseModel, AbstractTotals):
    __tablename__ = "reports_reportleveltotals"
    report_id = Column(types.BigInteger, ForeignKey("reports_commitreport.id"))
    report = relationship("CommitReport", foreign_keys=[report_id])


class UploadLevelTotals(CodecovBaseModel, AbstractTotals):
    __tablename__ = "reports_uploadleveltotals"
    upload_id = Column("upload_id", types.BigInteger, ForeignKey("reports_upload.id"))
    upload = relationship("Upload", foreign_keys=[upload_id])


class CompareFlag(MixinBaseClass, CodecovBaseModel):
    __tablename__ = "compare_flagcomparison"

    commit_comparison_id = Column(
        types.BigInteger, ForeignKey("compare_commitcomparison.id")
    )
    repositoryflag_id = Column(
        types.BigInteger, ForeignKey("reports_repositoryflag.id")
    )
    head_totals = Column(postgresql.JSON)
    base_totals = Column(postgresql.JSON)
    patch_totals = Column(postgresql.JSON)

    commit_comparison = relationship(CompareCommit, foreign_keys=[commit_comparison_id])
    repositoryflag = relationship(RepositoryFlag, foreign_keys=[repositoryflag_id])


class CompareComponent(MixinBaseClass, CodecovBaseModel):
    __tablename__ = "compare_componentcomparison"

    commit_comparison_id = Column(
        types.BigInteger, ForeignKey("compare_commitcomparison.id")
    )
    component_id = Column(types.String(100), nullable=False)
    head_totals = Column(postgresql.JSON)
    base_totals = Column(postgresql.JSON)
    patch_totals = Column(postgresql.JSON)

    commit_comparison = relationship(CompareCommit, foreign_keys=[commit_comparison_id])


class Test(CodecovBaseModel):
    __tablename__ = "reports_test"
    # the reason we aren't using the regular primary key
    # in this case is because we want to be able to compute/predict
    # the primary key of a Test object ourselves in the processor
    # so we can easily do concurrent writes to the database
    # this is a hash of the repoid, name, testsuite and env
    id_ = Column("id", types.Text, primary_key=True)
    external_id = Column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )
    created_at = Column(types.DateTime(timezone=True), default=get_utc_now)
    updated_at = Column(
        types.DateTime(timezone=True), onupdate=get_utc_now, default=get_utc_now
    )

    @property
    def id(self):
        return self.id_

    repoid = Column(types.Integer, ForeignKey("repos.repoid"))
    repository = relationship("Repository", backref=backref("tests"))
    name = Column(types.String(256), nullable=False)
    testsuite = Column(types.String(256), nullable=False)
    # this is a hash of the flags associated with this test
    # users will use flags to distinguish the same test being run
    # in a different environment
    # for example: the same test being run on windows vs. mac
    flags_hash = Column(types.String(256), nullable=False)

    framework = Column(types.String(100), nullable=True)

    computed_name = Column(types.Text, nullable=True)
    filename = Column(types.Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "repoid",
            "name",
            "testsuite",
            "flags_hash",
            name="reports_test_repoid_name_testsuite_flags_hash",
        ),
    )


class TestInstance(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_testinstance"
    test_id = Column(types.Text, ForeignKey("reports_test.id"))
    test = relationship(Test, backref=backref("testinstances"))
    duration_seconds = Column(types.Float, nullable=False)
    outcome = Column(types.String(100), nullable=False)
    upload_id = Column(types.BigInteger, ForeignKey("reports_upload.id"))
    upload = relationship("Upload", backref=backref("testinstances"))
    failure_message = Column(types.Text)
    branch = Column(types.Text, nullable=True)
    commitid = Column(types.Text, nullable=True)
    repoid = Column(types.Integer, nullable=True)

    reduced_error_id = Column(
        types.BigInteger, ForeignKey("reports_reducederror.id"), nullable=True
    )
    reduced_error = relationship("ReducedError", backref=backref("testinstances"))


class TestResultReportTotals(CodecovBaseModel, MixinBaseClass):
    __tablename__ = "reports_testresultreporttotals"
    report_id = Column(types.BigInteger, ForeignKey("reports_commitreport.id"))
    report = relationship("CommitReport", foreign_keys=[report_id])
    passed = Column(types.Integer)
    skipped = Column(types.Integer)
    failed = Column(types.Integer)

    # this field is no longer used in the new ta_finisher task
    # TODO: thus, it will be removed in the future
    error = Column(types.String(100), nullable=True)


class ReducedError(CodecovBaseModel):
    __tablename__ = "reports_reducederror"
    id_ = Column("id", types.BigInteger, primary_key=True)
    message = Column(types.Text)
    created_at = Column(types.DateTime(timezone=True), default=get_utc_now)
    updated_at = Column(
        types.DateTime(timezone=True), onupdate=get_utc_now, default=get_utc_now
    )

    @property
    def id(self):
        return self.id_


class Flake(CodecovBaseModel):
    __tablename__ = "reports_flake"
    id_ = Column("id", types.BigInteger, primary_key=True)
    repoid = Column(types.Integer, ForeignKey("repos.repoid"))
    repository = relationship("Repository", backref=backref("flakes"))

    testid = Column(types.Text, ForeignKey("reports_test.id"))
    test = relationship(Test, backref=backref("flakes"))

    reduced_error_id = Column(
        types.BigInteger, ForeignKey("reports_reducederror.id"), nullable=True
    )
    reduced_error = relationship(ReducedError, backref=backref("flakes"))

    recent_passes_count = Column(types.Integer)
    count = Column(types.Integer)
    fail_count = Column(types.Integer)
    start_date = Column(types.DateTime)
    end_date = Column(types.DateTime, nullable=True)

    @property
    def id(self):
        return self.id_


class DailyTestRollup(CodecovBaseModel, MixinBaseClassNoExternalID):
    __tablename__ = "reports_dailytestrollups"

    test_id = Column(types.Text, ForeignKey("reports_test.id"))
    test = relationship(Test, backref=backref("dailytestrollups"))
    date = Column(types.Date)
    repoid = Column(types.Integer)
    branch = Column(types.Text)

    fail_count = Column(types.Integer)
    flaky_fail_count = Column(types.Integer)
    skip_count = Column(types.Integer)
    pass_count = Column(types.Integer)
    last_duration_seconds = Column(types.Float)
    avg_duration_seconds = Column(types.Float)
    latest_run = Column(types.DateTime)
    commits_where_fail = Column(types.ARRAY(types.Text))

    __table_args__ = (
        UniqueConstraint(
            "repoid",
            "date",
            "branch",
            "test_id",
            name="reports_dailytestrollups_repoid_date_branch_test",
        ),
    )


class TestFlagBridge(CodecovBaseModel):
    __tablename__ = "reports_test_results_flag_bridge"

    id_ = Column("id", types.BigInteger, primary_key=True)

    test_id = Column(types.Text, ForeignKey("reports_test.id"))
    test = relationship(Test, backref=backref("test_flag_bridges"))

    flag_id = Column(
        "flag_id", types.BigInteger, ForeignKey("reports_repositoryflag.id")
    )
    flag = relationship("RepositoryFlag", backref=backref("test_flag_bridges"))
