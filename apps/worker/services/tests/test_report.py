from decimal import Decimal
from unittest import mock

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from database.models import CommitReport, RepositoryFlag, Upload
from database.tests.factories import CommitFactory
from helpers.exceptions import RepositoryWithoutValidBotError
from services.processing.merging import clear_carryforward_sessions
from services.report import NotReadyToBuildReportYetError, ReportService
from services.report import log as report_log
from shared.api_archive.archive import ArchiveService
from shared.reports.resources import Report, ReportFile, Session, SessionType
from shared.reports.test_utils import convert_report_to_better_readable
from shared.reports.types import ReportLine, ReportTotals
from shared.torngit.exceptions import TorngitRateLimitError
from shared.yaml import UserYaml


@pytest.fixture
def sample_report():
    report = Report()
    first_file = ReportFile("file_1.go")
    first_file.append(1, ReportLine.create(1, sessions=[[0, 1]], complexity=(10, 2)))
    first_file.append(2, ReportLine.create(0, sessions=[[0, 1]]))
    first_file.append(3, ReportLine.create(1, sessions=[[0, 1]]))
    first_file.append(5, ReportLine.create(1, sessions=[[0, 1], [1, 1]]))
    first_file.append(6, ReportLine.create(0, sessions=[[0, 1]]))
    first_file.append(8, ReportLine.create(1, sessions=[[0, 1], [1, 0]]))
    first_file.append(9, ReportLine.create(1, sessions=[[0, 1]]))
    first_file.append(10, ReportLine.create(0, sessions=[[0, 1]]))
    second_file = ReportFile("file_2.py")
    second_file.append(12, ReportLine.create(1, sessions=[[0, 1]]))
    second_file.append(51, ReportLine.create("1/2", type="b", sessions=[[0, 1]]))
    report.append(first_file)
    report.append(second_file)
    report.add_session(
        Session(
            flags=["unit"],
            provider="circleci",
            session_type=SessionType.uploaded,
            build="aycaramba",
            totals=ReportTotals(2, 10),
        )
    )
    report.add_session(
        Session(
            flags=["integration"],
            provider="travis",
            session_type=SessionType.carriedforward,
            build="poli",
        )
    )
    return report


@pytest.fixture
def sample_commit_with_report_big(dbsession, mock_storage):
    sessions_dict = {
        "0": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": [],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
        "1": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["unit"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
        "2": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["enterprise"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
        "3": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["unit", "enterprise"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
    }
    file_headers = {
        "file_00.py": [
            0,
            [0, 14, 12, 0, 2, "85.71429", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_01.py": [
            1,
            [0, 11, 8, 0, 3, "72.72727", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_02.py": [
            2,
            [0, 13, 9, 0, 4, "69.23077", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_03.py": [
            3,
            [0, 16, 8, 0, 8, "50.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_04.py": [
            4,
            [0, 10, 6, 0, 4, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_05.py": [
            5,
            [0, 14, 10, 0, 4, "71.42857", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_06.py": [
            6,
            [0, 9, 7, 1, 1, "77.77778", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_07.py": [
            7,
            [0, 11, 9, 0, 2, "81.81818", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_08.py": [
            8,
            [0, 11, 6, 0, 5, "54.54545", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_09.py": [
            9,
            [0, 14, 10, 1, 3, "71.42857", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_10.py": [
            10,
            [0, 10, 6, 1, 3, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_11.py": [
            11,
            [0, 23, 15, 1, 7, "65.21739", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_12.py": [
            12,
            [0, 14, 8, 0, 6, "57.14286", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_13.py": [
            13,
            [0, 15, 9, 0, 6, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_14.py": [
            14,
            [0, 23, 13, 0, 10, "56.52174", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
    }
    commit = CommitFactory.create(
        _report_json={"sessions": sessions_dict, "files": file_headers}
    )
    dbsession.add(commit)
    dbsession.flush()
    with open("tasks/tests/samples/sample_chunks_4_sessions.txt", "rb") as f:
        archive_service = ArchiveService(commit.repository)
        archive_service.write_chunks(commit.commitid, f.read())
    return commit


@pytest.fixture
def sample_commit_with_report_big_with_labels(dbsession, mock_storage):
    sessions_dict = {
        "0": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["enterprise"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
    }
    file_headers = {
        "file_00.py": [
            0,
            [0, 4, 0, 4, 0, "0", 0, 0, 0, 0, 0, 0, 0],
            [[0, 4, 0, 4, 0, "0", 0, 0, 0, 0, 0, 0, 0]],
            None,
        ],
        "file_01.py": [
            1,
            [0, 32, 32, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
            [[0, 32, 32, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0]],
            None,
        ],
    }
    commit = CommitFactory.create(
        _report_json={"sessions": sessions_dict, "files": file_headers}
    )
    dbsession.add(commit)
    dbsession.flush()
    with open("tasks/tests/samples/sample_chunks_with_header.txt", "rb") as f:
        archive_service = ArchiveService(commit.repository)
        archive_service.write_chunks(commit.commitid, f.read())
    return commit


@pytest.fixture
def sample_commit_with_report_big_already_carriedforward(dbsession, mock_storage):
    sessions_dict = {
        "0": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": [],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
        "1": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["unit"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "t": None,
            "u": None,
        },
        "2": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["enterprise"],
            "j": None,
            "n": None,
            "p": None,
            "st": "carriedforward",
            "t": None,
            "u": None,
        },
        "3": {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["unit", "enterprise"],
            "j": None,
            "n": None,
            "p": None,
            "st": "carriedforward",
            "t": None,
            "u": None,
        },
    }
    file_headers = {
        "file_00.py": [
            0,
            [0, 14, 12, 0, 2, "85.71429", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_01.py": [
            1,
            [0, 11, 8, 0, 3, "72.72727", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_10.py": [
            10,
            [0, 10, 6, 1, 3, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_11.py": [
            11,
            [0, 23, 15, 1, 7, "65.21739", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_12.py": [
            12,
            [0, 14, 8, 0, 6, "57.14286", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_13.py": [
            13,
            [0, 15, 9, 0, 6, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_14.py": [
            14,
            [0, 23, 13, 0, 10, "56.52174", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_02.py": [
            2,
            [0, 13, 9, 0, 4, "69.23077", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_03.py": [
            3,
            [0, 16, 8, 0, 8, "50.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_04.py": [
            4,
            [0, 10, 6, 0, 4, "60.00000", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_05.py": [
            5,
            [0, 14, 10, 0, 4, "71.42857", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_06.py": [
            6,
            [0, 9, 7, 1, 1, "77.77778", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_07.py": [
            7,
            [0, 11, 9, 0, 2, "81.81818", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_08.py": [
            8,
            [0, 11, 6, 0, 5, "54.54545", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
        "file_09.py": [
            9,
            [0, 14, 10, 1, 3, "71.42857", 0, 0, 0, 0, 0, 0, 0],
            None,
        ],
    }
    commit = CommitFactory.create(
        _report_json={"sessions": sessions_dict, "files": file_headers}
    )
    dbsession.add(commit)
    dbsession.flush()
    with open("tasks/tests/samples/sample_chunks_4_sessions.txt", "rb") as f:
        archive_service = ArchiveService(commit.repository)
        archive_service.write_chunks(commit.commitid, f.read())
    return commit


class TestReportService:
    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit(
        self,
        dbsession,
        sample_commit_with_report_big,
        mock_storage,
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        assert sorted(report.files) == sorted(
            [
                "file_00.py",
                "file_01.py",
                "file_02.py",
                "file_03.py",
                "file_04.py",
                "file_05.py",
                "file_06.py",
                "file_07.py",
                "file_08.py",
                "file_09.py",
                "file_10.py",
                "file_11.py",
                "file_12.py",
                "file_13.py",
                "file_14.py",
            ]
        )
        assert report.totals == ReportTotals(
            files=15,
            lines=188,
            hits=68,
            misses=26,
            partials=94,
            coverage="36.17021",
            branches=0,
            methods=0,
            messages=0,
            sessions=2,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)

        assert readable_report == {
            "archive": {
                "file_00.py": [
                    (1, 1, None, [[2, 1]], None, None),
                    (2, 1, None, [[2, 1]], None, None),
                    (3, "1/3", None, [[2, "1/3"]], None, None),
                    (4, "1/2", None, [[3, "1/2"]], None, None),
                    (5, 0, None, [[3, 0]], None, None),
                    (6, 0, None, [[2, 0]], None, None),
                    (7, 0, None, [[3, 0]], None, None),
                    (8, 0, None, [[3, 0]], None, None),
                    (9, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (10, 0, None, [[2, 0]], None, None),
                    (11, "1/2", None, [[2, "1/2"]], None, None),
                    (12, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (13, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (14, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                ],
                "file_01.py": [
                    (2, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (3, "1/2", None, [[3, "1/2"]], None, None),
                    (4, "1/2", None, [[3, "1/2"]], None, None),
                    (5, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (6, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (7, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (8, 1, None, [[2, 1]], None, None),
                    (9, 1, None, [[2, 1]], None, None),
                    (10, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (11, 1, None, [[3, 0], [2, 1]], None, None),
                ],
                "file_02.py": [
                    (1, 1, None, [[2, 1]], None, None),
                    (2, "1/3", None, [[3, "1/3"]], None, None),
                    (4, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (5, 1, None, [[3, 1]], None, None),
                    (6, "1/3", None, [[2, "1/3"]], None, None),
                    (8, 1, None, [[2, 1]], None, None),
                    (9, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (10, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (11, "1/2", None, [[2, "1/2"]], None, None),
                    (12, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (13, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                ],
                "file_03.py": [
                    (2, 1, None, [[3, 0], [2, 1]], None, None),
                    (3, "1/2", None, [[3, "1/2"]], None, None),
                    (4, 0, None, [[3, 0]], None, None),
                    (5, "1/3", None, [[2, "1/3"]], None, None),
                    (6, "1/3", None, [[3, "1/3"]], None, None),
                    (7, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (8, 0, None, [[3, 0]], None, None),
                    (9, "1/3", None, [[3, "1/3"]], None, None),
                    (10, "1/3", None, [[2, "1/3"]], None, None),
                    (11, "1/2", None, [[2, "1/2"]], None, None),
                    (12, "1/2", None, [[3, "1/2"]], None, None),
                    (13, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (14, "1/2", None, [[3, "1/2"]], None, None),
                    (15, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (16, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                ],
                "file_04.py": [
                    (1, "1/3", None, [[2, "1/3"]], None, None),
                    (2, 0, None, [[3, 0]], None, None),
                    (3, "1/2", None, [[2, "1/2"]], None, None),
                    (4, "1/2", None, [[2, "1/2"]], None, None),
                    (5, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (6, "1/2", None, [[3, "1/2"]], None, None),
                    (7, 1, None, [[3, 0], [2, 1]], None, None),
                    (8, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (9, "1/3", None, [[2, "1/3"]], None, None),
                    (10, "1/2", None, [[2, "1/2"]], None, None),
                ],
                "file_05.py": [
                    (2, 0, None, [[2, 0]], None, None),
                    (3, "1/2", None, [[2, "1/2"]], None, None),
                    (4, 0, None, [[3, 0]], None, None),
                    (5, "1/3", None, [[3, "1/3"]], None, None),
                    (6, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (7, "1/3", None, [[3, "1/3"]], None, None),
                    (8, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (9, "1/3", None, [[2, "1/3"]], None, None),
                    (10, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (11, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (12, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (13, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (14, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                ],
                "file_06.py": [
                    (3, "1/2", None, [[3, "1/2"]], None, None),
                    (4, 1, None, [[3, 1]], None, None),
                    (5, 1, None, [[3, 1]], None, None),
                    (6, 1, None, [[2, 1]], None, None),
                    (7, 1, None, [[3, 1]], None, None),
                    (8, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (9, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                ],
                "file_07.py": [
                    (1, 1, None, [[3, 1]], None, None),
                    (2, 1, None, [[2, 0], [3, 1]], None, None),
                    (3, 1, None, [[2, 1]], None, None),
                    (4, "1/2", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (5, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (6, 0, None, [[2, 0]], None, None),
                    (7, "1/3", None, [[3, "1/3"]], None, None),
                    (8, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (9, "1/3", None, [[2, "1/3"]], None, None),
                    (10, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (11, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                ],
                "file_08.py": [
                    (1, 0, None, [[3, 0]], None, None),
                    (2, 0, None, [[2, 0]], None, None),
                    (3, 0, None, [[2, 0]], None, None),
                    (4, "1/3", None, [[2, "1/3"]], None, None),
                    (5, "1/2", None, [[3, "1/2"]], None, None),
                    (6, 0, None, [[2, 0]], None, None),
                    (7, 1, None, [[2, 0], [3, 1]], None, None),
                    (8, 1, None, [[3, 0], [2, 1]], None, None),
                    (9, "1/2", None, [[3, "1/2"]], None, None),
                    (10, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (11, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                ],
                "file_09.py": [
                    (1, 0, None, [[2, 0]], None, None),
                    (3, "1/3", None, [[3, "1/3"]], None, None),
                    (6, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (7, "1/2", None, [[2, "1/2"]], None, None),
                    (8, "1/2", None, [[2, "1/2"]], None, None),
                    (9, 1, None, [[2, 1]], None, None),
                    (10, 1, None, [[2, 0], [3, 1]], None, None),
                    (11, "1/3", None, [[2, "1/3"]], None, None),
                    (12, "1/3", None, [[3, "1/3"]], None, None),
                    (13, 1, None, [[2, 0], [3, 1]], None, None),
                    (14, 1, None, [[3, 0], [2, 1]], None, None),
                ],
                "file_10.py": [
                    (2, 1, None, [[3, 1]], None, None),
                    (3, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (4, "1/2", None, [[2, "1/2"]], None, None),
                    (6, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (7, 1, None, [[3, 1]], None, None),
                    (8, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (9, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (10, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                ],
                "file_11.py": [
                    (1, 0, None, [[3, 0]], None, None),
                    (3, "1/2", None, [[2, "1/2"]], None, None),
                    (4, "1/2", None, [[3, "1/2"]], None, None),
                    (5, 0, None, [[2, 0]], None, None),
                    (6, 0, None, [[3, 0]], None, None),
                    (7, "1/3", None, [[2, "1/3"]], None, None),
                    (8, 1, None, [[2, 1]], None, None),
                    (9, "1/2", None, [[2, "1/2"]], None, None),
                    (10, 1, None, [[3, 1]], None, None),
                    (11, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (12, 1, None, [[3, 1]], None, None),
                    (13, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (14, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (15, 0, None, [[2, 0]], None, None),
                    (16, 1, None, [[2, 0], [3, 1]], None, None),
                    (17, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (18, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (19, 0, None, [[3, 0]], None, None),
                    (20, 1, None, [[3, 1]], None, None),
                    (21, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (22, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (23, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                ],
                "file_12.py": [
                    (2, "1/2", None, [[3, "1/2"]], None, None),
                    (3, "1/3", None, [[3, "1/3"]], None, None),
                    (4, 0, None, [[2, 0]], None, None),
                    (5, 0, None, [[3, 0]], None, None),
                    (7, 1, None, [[3, 1]], None, None),
                    (8, "1/2", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (9, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (10, 0, None, [[3, 0]], None, None),
                    (11, "1/3", None, [[3, "1/3"]], None, None),
                    (12, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (13, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (14, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                ],
                "file_13.py": [
                    (2, 1, None, [[3, 1]], None, None),
                    (6, 1, None, [[3, 0], [2, 1]], None, None),
                    (7, "1/3", None, [[2, "1/3"]], None, None),
                    (8, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (9, 1, None, [[3, 0], [2, 1]], None, None),
                    (10, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (11, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (12, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (13, "1/2", None, [[3, "1/2"]], None, None),
                    (14, 1, None, [[3, 1]], None, None),
                    (15, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                ],
                "file_14.py": [
                    (1, 1, None, [[2, 1]], None, None),
                    (2, 0, None, [[2, 0]], None, None),
                    (3, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (5, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (6, "1/3", None, [[3, "1/3"]], None, None),
                    (7, 1, None, [[2, 1]], None, None),
                    (8, "1/3", None, [[2, "1/3"]], None, None),
                    (9, "1/2", None, [[2, "1/2"]], None, None),
                    (10, 1, None, [[2, 1]], None, None),
                    (11, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (12, 1, None, [[2, 0], [3, 1]], None, None),
                    (13, "1/3", None, [[3, "1/3"]], None, None),
                    (14, "1/3", None, [[3, "1/3"]], None, None),
                    (15, 0, None, [[2, 0]], None, None),
                    (16, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (17, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (18, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (19, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (20, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (21, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (22, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (23, 1, None, [[2, 0], [3, 1]], None, None),
                ],
            },
            "report": {
                "files": {
                    "file_00.py": [
                        0,
                        [0, 14, 4, 5, 5, "28.57143", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_01.py": [
                        1,
                        [0, 10, 3, 0, 7, "30.00000", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_02.py": [
                        2,
                        [0, 11, 5, 0, 6, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_03.py": [
                        3,
                        [0, 15, 4, 2, 9, "26.66667", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_04.py": [
                        4,
                        [0, 10, 3, 1, 6, "30.00000", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_05.py": [
                        5,
                        [0, 13, 3, 2, 8, "23.07692", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_06.py": [
                        6,
                        [0, 7, 5, 0, 2, "71.42857", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_07.py": [
                        7,
                        [0, 11, 5, 1, 5, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_08.py": [
                        8,
                        [0, 11, 2, 4, 5, "18.18182", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_09.py": [
                        9,
                        [0, 11, 5, 1, 5, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_10.py": [
                        10,
                        [0, 8, 3, 0, 5, "37.50000", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_11.py": [
                        11,
                        [0, 22, 8, 5, 9, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_12.py": [
                        12,
                        [0, 12, 4, 3, 5, "33.33333", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_13.py": [
                        13,
                        [0, 11, 6, 0, 5, "54.54545", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_14.py": [
                        14,
                        [0, 22, 8, 2, 12, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {
                    "2": {
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["enterprise"],
                        "j": None,
                        "N": "Carriedforward",
                        "n": None,
                        "p": None,
                        "se": {"carriedforward_from": parent_commit.commitid},
                        "st": "carriedforward",
                        "t": None,
                        "u": None,
                    },
                    "3": {
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["unit", "enterprise"],
                        "j": None,
                        "N": "Carriedforward",
                        "n": None,
                        "p": None,
                        "se": {"carriedforward_from": parent_commit.commitid},
                        "st": "carriedforward",
                        "t": None,
                        "u": None,
                    },
                },
            },
            "totals": {
                "b": 0,
                "c": "36.17021",
                "C": 0,
                "d": 0,
                "diff": None,
                "f": 15,
                "h": 68,
                "M": 0,
                "m": 26,
                "N": 0,
                "n": 188,
                "p": 94,
                "s": 2,
            },
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_with_labels(
        self, dbsession, sample_commit_with_report_big_with_labels
    ):
        parent_commit = sample_commit_with_report_big_with_labels
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        assert sorted(report.files) == ["file_00.py", "file_01.py"]

        assert report.totals == ReportTotals(
            files=2,
            lines=36,
            hits=32,
            misses=4,
            partials=0,
            coverage="88.88889",
            branches=0,
            methods=0,
            messages=0,
            sessions=1,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)
        assert readable_report == {
            "archive": {
                "file_00.py": [
                    (1, 0, None, [[0, 0]], None, None),
                    (3, 0, None, [[0, 0]], None, None),
                    (4, 0, None, [[0, 0]], None, None),
                    (5, 0, None, [[0, 0]], None, None),
                ],
                "file_01.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (2, 1, None, [[0, 1]], None, None),
                    (5, 1, None, [[0, 1]], None, None),
                    (6, 1, None, [[0, 1]], None, None),
                    (7, 1, None, [[0, 1]], None, None),
                    (8, 1, None, [[0, 1]], None, None),
                    (9, 1, None, [[0, 1]], None, None),
                    (12, 1, None, [[0, 1]], None, None),
                    (13, 1, None, [[0, 1]], None, None),
                    (14, 1, None, [[0, 1]], None, None),
                    (16, 1, None, [[0, 1]], None, None),
                    (17, 1, None, [[0, 1]], None, None),
                    (18, 1, None, [[0, 1]], None, None),
                    (19, 1, None, [[0, 1]], None, None),
                    (21, 1, None, [[0, 1]], None, None),
                    (22, 1, None, [[0, 1]], None, None),
                    (23, 1, None, [[0, 1]], None, None),
                    (25, 1, None, [[0, 1]], None, None),
                    (26, 1, None, [[0, 1]], None, None),
                    (27, 1, None, [[0, 1]], None, None),
                    (29, 1, None, [[0, 1]], None, None),
                    (30, 1, None, [[0, 1]], None, None),
                    (31, 1, None, [[0, 1]], None, None),
                    (33, 1, None, [[0, 1]], None, None),
                    (34, 1, None, [[0, 1]], None, None),
                    (36, 1, None, [[0, 1]], None, None),
                    (37, 1, None, [[0, 1]], None, None),
                    (38, 1, None, [[0, 1]], None, None),
                    (39, 1, None, [[0, 1]], None, None),
                    (41, 1, None, [[0, 1]], None, None),
                    (43, 1, None, [[0, 1]], None, None),
                    (44, 0, None, [[0, 0]], None, None),
                ],
            },
            "report": {
                "files": {
                    "file_00.py": [
                        0,
                        [0, 4, 0, 4, 0, "0", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_01.py": [
                        1,
                        [0, 32, 32, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {
                    "0": {
                        "N": "Carriedforward",
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["enterprise"],
                        "j": None,
                        "n": None,
                        "p": None,
                        "se": {"carriedforward_from": parent_commit.commitid},
                        "st": "carriedforward",
                        "t": None,
                        "u": None,
                    }
                },
            },
            "totals": {
                "C": 0,
                "M": 0,
                "N": 0,
                "b": 0,
                "c": "88.88889",
                "d": 0,
                "diff": None,
                "f": 2,
                "h": 32,
                "m": 4,
                "n": 36,
                "p": 0,
                "s": 1,
            },
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_build_report_from_commit_carriedforward_add_sessions(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml = UserYaml({"flags": {"enterprise": {"carryforward": True}}})

        def fake_possibly_shift(report, base, head):
            return report

        mock_possibly_shift = mocker.patch.object(
            ReportService,
            "_possibly_shift_carryforward_report",
            side_effect=fake_possibly_shift,
        )
        report = ReportService(yaml).create_new_report_for_commit(commit)
        assert report is not None
        assert len(report.files) == 15
        mock_possibly_shift.assert_called()
        to_merge_session = Session(flags=["enterprise"])
        report.add_session(to_merge_session)
        assert sorted(report.sessions.keys()) == [2, 3, 4]
        assert clear_carryforward_sessions(report, ["enterprise"], yaml) == {2, 3}
        assert sorted(report.sessions.keys()) == [4]
        readable_report = convert_report_to_better_readable(report)
        assert readable_report == {
            "archive": {},
            "report": {
                "files": {},
                "sessions": {
                    "4": {
                        "N": None,
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["enterprise"],
                        "j": None,
                        "n": None,
                        "p": None,
                        "st": "uploaded",
                        "se": {},
                        "t": None,
                        "u": None,
                    }
                },
            },
            "totals": {
                "C": 0,
                "M": 0,
                "N": 0,
                "b": 0,
                "c": None,
                "d": 0,
                "diff": None,
                "f": 0,
                "h": 0,
                "m": 0,
                "n": 0,
                "p": 0,
                "s": 1,
            },
        }

    def test_get_existing_report_for_commit_already_carriedforward_add_sessions(
        self, dbsession, sample_commit_with_report_big_already_carriedforward
    ):
        commit = sample_commit_with_report_big_already_carriedforward
        dbsession.add(commit)
        dbsession.flush()
        yaml = UserYaml({"flags": {"enterprise": {"carryforward": True}}})
        report = ReportService(yaml).get_existing_report_for_commit(commit)
        assert report is not None
        assert len(report.files) == 15
        assert sorted(report.sessions.keys()) == [0, 1, 2, 3]
        first_to_merge_session = Session(flags=["enterprise"])
        report.add_session(first_to_merge_session)
        assert sorted(report.sessions.keys()) == [0, 1, 2, 3, 4]
        assert clear_carryforward_sessions(report, {"enterprise"}, yaml) == {2, 3}
        assert sorted(report.sessions.keys()) == [0, 1, 4]
        readable_report = convert_report_to_better_readable(report)
        expected_sessions_dict = {
            "0": {
                "N": None,
                "a": None,
                "c": None,
                "d": None,
                "e": None,
                "f": None,
                "j": None,
                "n": None,
                "p": None,
                "st": "uploaded",
                "se": {},
                "t": None,
                "u": None,
            },
            "1": {
                "N": None,
                "a": None,
                "c": None,
                "d": None,
                "e": None,
                "f": ["unit"],
                "j": None,
                "n": None,
                "p": None,
                "st": "uploaded",
                "se": {},
                "t": None,
                "u": None,
            },
            "4": {
                "N": None,
                "a": None,
                "c": None,
                "d": None,
                "e": None,
                "f": ["enterprise"],
                "j": None,
                "n": None,
                "p": None,
                "st": "uploaded",
                "se": {},
                "t": None,
                "u": None,
            },
        }
        assert readable_report["report"]["sessions"] == expected_sessions_dict

        newly_added_session = {
            "N": None,
            "a": None,
            "c": None,
            "d": None,
            "e": None,
            "f": ["unit"],
            "j": None,
            "n": None,
            "p": None,
            "st": "uploaded",
            "se": {},
            "t": None,
            "u": None,
        }
        second_to_merge_session = Session(flags=["unit"])
        report.add_session(second_to_merge_session)
        assert sorted(report.sessions.keys()) == [0, 1, 3, 4]
        assert clear_carryforward_sessions(report, {"unit"}, yaml) == set()
        assert sorted(report.sessions.keys()) == [0, 1, 3, 4]
        new_readable_report = convert_report_to_better_readable(report)
        assert len(new_readable_report["report"]["sessions"]) == 4
        assert (
            new_readable_report["report"]["sessions"]["0"]
            == expected_sessions_dict["0"]
        )
        assert (
            new_readable_report["report"]["sessions"]["1"]
            == expected_sessions_dict["1"]
        )
        assert (
            new_readable_report["report"]["sessions"]["4"]
            == expected_sessions_dict["4"]
        )
        assert new_readable_report["report"]["sessions"]["3"] == newly_added_session

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_with_path_filters(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {
            "flags": {
                "enterprise": {"carryforward": True, "paths": ["file_1.*"]},
                "special_flag": {"paths": ["file_0.*"]},
            }
        }

        def fake_possibly_shift(report, base, head):
            return report

        mock_possibly_shift = mocker.patch.object(
            ReportService,
            "_possibly_shift_carryforward_report",
            side_effect=fake_possibly_shift,
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        assert sorted(report.files) == sorted(
            ["file_10.py", "file_11.py", "file_12.py", "file_13.py", "file_14.py"]
        )
        mock_possibly_shift.assert_called()
        assert report.totals == ReportTotals(
            files=5,
            lines=75,
            hits=29,
            misses=10,
            partials=36,
            coverage="38.66667",
            branches=0,
            methods=0,
            messages=0,
            sessions=2,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)

        assert readable_report == {
            "archive": {
                "file_10.py": [
                    (2, 1, None, [[3, 1]], None, None),
                    (3, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (4, "1/2", None, [[2, "1/2"]], None, None),
                    (6, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (7, 1, None, [[3, 1]], None, None),
                    (8, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (9, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (10, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                ],
                "file_11.py": [
                    (1, 0, None, [[3, 0]], None, None),
                    (3, "1/2", None, [[2, "1/2"]], None, None),
                    (4, "1/2", None, [[3, "1/2"]], None, None),
                    (5, 0, None, [[2, 0]], None, None),
                    (6, 0, None, [[3, 0]], None, None),
                    (7, "1/3", None, [[2, "1/3"]], None, None),
                    (8, 1, None, [[2, 1]], None, None),
                    (9, "1/2", None, [[2, "1/2"]], None, None),
                    (10, 1, None, [[3, 1]], None, None),
                    (11, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (12, 1, None, [[3, 1]], None, None),
                    (13, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (14, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (15, 0, None, [[2, 0]], None, None),
                    (16, 1, None, [[2, 0], [3, 1]], None, None),
                    (17, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (18, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (19, 0, None, [[3, 0]], None, None),
                    (20, 1, None, [[3, 1]], None, None),
                    (21, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                    (22, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (23, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                ],
                "file_12.py": [
                    (2, "1/2", None, [[3, "1/2"]], None, None),
                    (3, "1/3", None, [[3, "1/3"]], None, None),
                    (4, 0, None, [[2, 0]], None, None),
                    (5, 0, None, [[3, 0]], None, None),
                    (7, 1, None, [[3, 1]], None, None),
                    (8, "1/2", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (9, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (10, 0, None, [[3, 0]], None, None),
                    (11, "1/3", None, [[3, "1/3"]], None, None),
                    (12, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (13, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (14, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                ],
                "file_13.py": [
                    (2, 1, None, [[3, 1]], None, None),
                    (6, 1, None, [[3, 0], [2, 1]], None, None),
                    (7, "1/3", None, [[2, "1/3"]], None, None),
                    (8, "3/3", None, [[2, 1], [3, "1/3"]], None, None),
                    (9, 1, None, [[3, 0], [2, 1]], None, None),
                    (10, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (11, "1/3", None, [[2, 0], [3, "1/3"]], None, None),
                    (12, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (13, "1/2", None, [[3, "1/2"]], None, None),
                    (14, 1, None, [[3, 1]], None, None),
                    (15, "2/2", None, [[3, 1], [2, "1/2"]], None, None),
                ],
                "file_14.py": [
                    (1, 1, None, [[2, 1]], None, None),
                    (2, 0, None, [[2, 0]], None, None),
                    (3, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (5, "2/2", None, [[2, 1], [3, "1/2"]], None, None),
                    (6, "1/3", None, [[3, "1/3"]], None, None),
                    (7, 1, None, [[2, 1]], None, None),
                    (8, "1/3", None, [[2, "1/3"]], None, None),
                    (9, "1/2", None, [[2, "1/2"]], None, None),
                    (10, 1, None, [[2, 1]], None, None),
                    (11, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (12, 1, None, [[2, 0], [3, 1]], None, None),
                    (13, "1/3", None, [[3, "1/3"]], None, None),
                    (14, "1/3", None, [[3, "1/3"]], None, None),
                    (15, 0, None, [[2, 0]], None, None),
                    (16, "1/2", None, [[2, 0], [3, "1/2"]], None, None),
                    (17, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (18, "1/3", None, [[3, 0], [2, "1/3"]], None, None),
                    (19, "1/2", None, [[3, 0], [2, "1/2"]], None, None),
                    (20, "3/3", None, [[3, 1], [2, "1/3"]], None, None),
                    (21, "1/3", None, [[2, "1/2"], [3, "1/3"]], None, None),
                    (22, "1/3", None, [[3, "1/2"], [2, "1/3"]], None, None),
                    (23, 1, None, [[2, 0], [3, 1]], None, None),
                ],
            },
            "report": {
                "files": {
                    "file_10.py": [
                        0,
                        [0, 8, 3, 0, 5, "37.50000", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_11.py": [
                        1,
                        [0, 22, 8, 5, 9, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_12.py": [
                        2,
                        [0, 12, 4, 3, 5, "33.33333", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_13.py": [
                        3,
                        [0, 11, 6, 0, 5, "54.54545", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "file_14.py": [
                        4,
                        [0, 22, 8, 2, 12, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {
                    "2": {
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["enterprise"],
                        "j": None,
                        "N": "Carriedforward",
                        "n": None,
                        "p": None,
                        "se": {"carriedforward_from": parent_commit.commitid},
                        "st": "carriedforward",
                        "t": None,
                        "u": None,
                    },
                    "3": {
                        "a": None,
                        "c": None,
                        "d": None,
                        "e": None,
                        "f": ["unit", "enterprise"],
                        "j": None,
                        "N": "Carriedforward",
                        "n": None,
                        "p": None,
                        "se": {"carriedforward_from": parent_commit.commitid},
                        "st": "carriedforward",
                        "t": None,
                        "u": None,
                    },
                },
            },
            "totals": {
                "b": 0,
                "c": "38.66667",
                "C": 0,
                "d": 0,
                "diff": None,
                "f": 5,
                "h": 29,
                "M": 0,
                "m": 10,
                "N": 0,
                "n": 75,
                "p": 36,
                "s": 2,
            },
        }

    def test_create_new_report_for_commit_no_flags(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        yaml_dict = {
            "flags": {
                "enterprise": {"paths": ["file_1.*"]},
                "special_flag": {"paths": ["file_0.*"]},
            }
        }
        mock_possibly_shift = mocker.patch.object(
            ReportService, "_possibly_shift_carryforward_report"
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        assert sorted(report.files) == []
        mock_possibly_shift.assert_not_called()
        assert report.totals == ReportTotals(
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            coverage=None,
            branches=0,
            methods=0,
            messages=0,
            sessions=0,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)
        assert readable_report == {
            "archive": {},
            "report": {"files": {}, "sessions": {}},
            "totals": {
                "C": 0,
                "M": 0,
                "N": 0,
                "b": 0,
                "c": None,
                "d": 0,
                "diff": None,
                "f": 0,
                "h": 0,
                "m": 0,
                "n": 0,
                "p": 0,
                "s": 0,
            },
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_no_parent(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=None,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        mock_possibly_shift = mocker.patch.object(
            ReportService, "_possibly_shift_carryforward_report"
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        assert sorted(report.files) == []
        mock_possibly_shift.assert_not_called()
        assert report.totals == ReportTotals(
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            coverage=None,
            branches=0,
            methods=0,
            messages=0,
            sessions=0,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)
        assert readable_report == {
            "archive": {},
            "report": {"files": {}, "sessions": {}},
            "totals": {
                "C": 0,
                "M": 0,
                "N": 0,
                "b": 0,
                "c": None,
                "d": 0,
                "diff": None,
                "f": 0,
                "h": 0,
                "m": 0,
                "n": 0,
                "p": 0,
                "s": 0,
            },
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_parent_not_ready(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        grandparent_commit = sample_commit_with_report_big
        parent_commit = CommitFactory.create(
            repository=grandparent_commit.repository,
            parent_commit_id=grandparent_commit.commitid,
            _report_json=None,
            state="pending",
        )
        commit = CommitFactory.create(
            repository=grandparent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        mock_possibly_shift = mocker.patch.object(
            ReportService, "_possibly_shift_carryforward_report"
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        mock_possibly_shift.assert_called()
        assert sorted(report.files) == [
            "file_00.py",
            "file_01.py",
            "file_02.py",
            "file_03.py",
            "file_04.py",
            "file_05.py",
            "file_06.py",
            "file_07.py",
            "file_08.py",
            "file_09.py",
            "file_10.py",
            "file_11.py",
            "file_12.py",
            "file_13.py",
            "file_14.py",
        ]
        assert report.totals == ReportTotals(
            files=15,
            lines=188,
            hits=68,
            misses=26,
            partials=94,
            coverage="36.17021",
            branches=0,
            methods=0,
            messages=0,
            sessions=2,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)
        assert readable_report["report"] == {
            "files": {
                "file_00.py": [
                    0,
                    [0, 14, 4, 5, 5, "28.57143", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_01.py": [
                    1,
                    [0, 10, 3, 0, 7, "30.00000", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_02.py": [
                    2,
                    [0, 11, 5, 0, 6, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_03.py": [
                    3,
                    [0, 15, 4, 2, 9, "26.66667", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_04.py": [
                    4,
                    [0, 10, 3, 1, 6, "30.00000", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_05.py": [
                    5,
                    [0, 13, 3, 2, 8, "23.07692", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_06.py": [
                    6,
                    [0, 7, 5, 0, 2, "71.42857", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_07.py": [
                    7,
                    [0, 11, 5, 1, 5, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_08.py": [
                    8,
                    [0, 11, 2, 4, 5, "18.18182", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_09.py": [
                    9,
                    [0, 11, 5, 1, 5, "45.45455", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_10.py": [
                    10,
                    [0, 8, 3, 0, 5, "37.50000", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_11.py": [
                    11,
                    [0, 22, 8, 5, 9, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_12.py": [
                    12,
                    [0, 12, 4, 3, 5, "33.33333", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_13.py": [
                    13,
                    [0, 11, 6, 0, 5, "54.54545", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
                "file_14.py": [
                    14,
                    [0, 22, 8, 2, 12, "36.36364", 0, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
            },
            "sessions": {
                "2": {
                    "a": None,
                    "c": None,
                    "d": None,
                    "e": None,
                    "f": ["enterprise"],
                    "j": None,
                    "N": "Carriedforward",
                    "n": None,
                    "p": None,
                    "se": {"carriedforward_from": grandparent_commit.commitid},
                    "st": "carriedforward",
                    "t": None,
                    "u": None,
                },
                "3": {
                    "a": None,
                    "c": None,
                    "d": None,
                    "e": None,
                    "f": ["unit", "enterprise"],
                    "j": None,
                    "N": "Carriedforward",
                    "n": None,
                    "p": None,
                    "se": {"carriedforward_from": grandparent_commit.commitid},
                    "st": "carriedforward",
                    "t": None,
                    "u": None,
                },
            },
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_parent_not_ready_but_skipped(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        parent_commit = sample_commit_with_report_big
        parent_commit.state = "skipped"
        dbsession.flush()
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        mock_possibly_shift = mocker.patch.object(
            ReportService, "_possibly_shift_carryforward_report"
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        mock_possibly_shift.assert_called()
        assert sorted(report.files) == sorted(
            [
                "file_00.py",
                "file_01.py",
                "file_02.py",
                "file_03.py",
                "file_04.py",
                "file_05.py",
                "file_06.py",
                "file_07.py",
                "file_08.py",
                "file_09.py",
                "file_10.py",
                "file_11.py",
                "file_12.py",
                "file_13.py",
                "file_14.py",
            ]
        )
        assert report.totals == ReportTotals(
            files=15,
            lines=188,
            hits=68,
            misses=26,
            partials=94,
            coverage="36.17021",
            branches=0,
            methods=0,
            messages=0,
            sessions=2,
            complexity=0,
            complexity_total=0,
            diff=0,
        )
        readable_report = convert_report_to_better_readable(report)
        expected_results_report = {
            "sessions": {
                "2": {
                    "N": "Carriedforward",
                    "a": None,
                    "c": None,
                    "d": readable_report["report"]["sessions"]["2"]["d"],
                    "e": None,
                    "f": ["enterprise"],
                    "j": None,
                    "n": None,
                    "p": None,
                    "st": "carriedforward",
                    "se": {"carriedforward_from": parent_commit.commitid},
                    "t": None,
                    "u": None,
                },
                "3": {
                    "N": "Carriedforward",
                    "a": None,
                    "c": None,
                    "d": readable_report["report"]["sessions"]["3"]["d"],
                    "e": None,
                    "f": ["unit", "enterprise"],
                    "j": None,
                    "n": None,
                    "p": None,
                    "st": "carriedforward",
                    "se": {"carriedforward_from": parent_commit.commitid},
                    "t": None,
                    "u": None,
                },
            }
        }
        assert (
            expected_results_report["sessions"]["2"]
            == readable_report["report"]["sessions"]["2"]
        )
        assert (
            expected_results_report["sessions"]["3"]
            == readable_report["report"]["sessions"]["3"]
        )
        assert (
            expected_results_report["sessions"] == readable_report["report"]["sessions"]
        )

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_too_many_ancestors_not_ready(
        self, dbsession, sample_commit_with_report_big, mocker
    ):
        grandparent_commit = sample_commit_with_report_big
        current_commit = grandparent_commit
        for i in range(10):
            current_commit = CommitFactory.create(
                repository=grandparent_commit.repository,
                parent_commit_id=current_commit.commitid,
                _report_json=None,
                state="pending",
            )
            dbsession.add(current_commit)
        commit = CommitFactory.create(
            repository=grandparent_commit.repository,
            parent_commit_id=current_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        mock_possibly_shift = mocker.patch.object(
            ReportService, "_possibly_shift_carryforward_report"
        )
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report is not None
        mock_possibly_shift.assert_not_called()
        assert sorted(report.files) == []
        readable_report = convert_report_to_better_readable(report)

        assert readable_report["report"] == {"files": {}, "sessions": {}}

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_parent_had_no_parent_and_pending(self, dbsession):
        current_commit = CommitFactory.create(parent_commit_id=None, state="pending")
        dbsession.add(current_commit)
        for i in range(5):
            current_commit = CommitFactory.create(
                repository=current_commit.repository,
                parent_commit_id=current_commit.commitid,
                _report_json=None,
                state="pending",
            )
            dbsession.add(current_commit)
        commit = CommitFactory.create(
            repository=current_commit.repository,
            parent_commit_id=current_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        with pytest.raises(NotReadyToBuildReportYetError):
            ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_potential_cf_but_not_real_cf(
        self, dbsession, sample_commit_with_report_big
    ):
        parent_commit = sample_commit_with_report_big
        dbsession.flush()
        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {
            "flag_management": {
                "default_rules": {"carryforward": False},
                "individual_flags": [{"name": "banana", "carryforward": True}],
            }
        }
        report = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert report.is_empty()

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_parent_has_no_report(
        self, mock_storage, dbsession
    ):
        parent = CommitFactory.create()
        dbsession.add(parent)
        dbsession.flush()
        commit = CommitFactory.create(
            parent_commit_id=parent.commitid, repository=parent.repository
        )
        dbsession.add(commit)
        dbsession.flush()
        report_service = ReportService(
            UserYaml({"flags": {"enterprise": {"carryforward": True}}})
        )
        r = report_service.create_new_report_for_commit(commit)
        assert r.files == []

    def test_save_full_report(
        self, dbsession, mock_storage, sample_report, mock_configuration
    ):
        mock_configuration.set_params(
            {
                "setup": {
                    "save_report_data_in_storage": {
                        "only_codecov": False,
                    },
                }
            }
        )
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        current_report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(current_report_row)
        dbsession.flush()
        sample_report.sessions[0].archive = "path/to/upload/location"
        sample_report.sessions[
            0
        ].name = "this name contains more than 100 chars 1111111111111111111111111111111111111111111111111111111111111this is more than 100"
        report_service = ReportService({})
        res = report_service.save_full_report(commit, sample_report)
        storage_hash = ArchiveService(commit.repository).storage_hash
        assert res == {
            "url": f"v4/repos/{storage_hash}/commits/{commit.commitid}/chunks.txt"
        }
        assert len(current_report_row.uploads) == 2
        first_upload = dbsession.query(Upload).filter_by(
            report_id=current_report_row.id_, provider="circleci"
        )[0]
        second_upload = dbsession.query(Upload).filter_by(
            report_id=current_report_row.id_, provider="travis"
        )[0]
        dbsession.refresh(second_upload)
        dbsession.refresh(first_upload)
        assert first_upload.build_code == "aycaramba"
        assert first_upload.build_url is None
        assert first_upload.env is None
        assert first_upload.job_code is None
        assert (
            first_upload.name
            == "this name contains more than 100 chars 1111111111111111111111111111111111111111111111111111111111111"
        )
        assert first_upload.provider == "circleci"
        assert first_upload.report_id == current_report_row.id_
        assert first_upload.state == "complete"
        assert first_upload.storage_path == "path/to/upload/location"
        assert first_upload.order_number == 0
        assert len(first_upload.flags) == 1
        assert first_upload.flags[0].repository == commit.repository
        assert first_upload.flags[0].flag_name == "unit"
        assert first_upload.totals is not None
        assert first_upload.totals.branches == 0
        assert first_upload.totals.coverage == Decimal("0.0")
        assert first_upload.totals.hits == 0
        assert first_upload.totals.lines == 10
        assert first_upload.totals.methods == 0
        assert first_upload.totals.misses == 0
        assert first_upload.totals.partials == 0
        assert first_upload.totals.files == 2
        assert first_upload.upload_extras == {}
        assert first_upload.upload_type == "uploaded"
        assert second_upload.build_code == "poli"
        assert second_upload.build_url is None
        assert second_upload.env is None
        assert second_upload.job_code is None
        assert second_upload.name is None
        assert second_upload.provider == "travis"
        assert second_upload.report_id == current_report_row.id_
        assert second_upload.state == "complete"
        assert second_upload.storage_path == ""
        assert second_upload.order_number == 1
        assert len(second_upload.flags) == 1
        assert second_upload.flags[0].repository == commit.repository
        assert second_upload.flags[0].flag_name == "integration"
        assert second_upload.totals is None
        assert second_upload.upload_extras == {}
        assert second_upload.upload_type == "carriedforward"

    def test_save_report_empty_report(self, dbsession, mock_storage):
        report = Report()
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        current_report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(current_report_row)
        dbsession.flush()
        report_service = ReportService({})
        res = report_service.save_report(commit, report)
        storage_hash = ArchiveService(commit.repository).storage_hash
        assert res == {
            "url": f"v4/repos/{storage_hash}/commits/{commit.commitid}/chunks.txt"
        }
        assert commit.totals == {
            "f": 0,
            "n": 0,
            "h": 0,
            "m": 0,
            "p": 0,
            "c": 0,
            "b": 0,
            "d": 0,
            "M": 0,
            "s": 0,
            "C": 0,
            "N": 0,
            "diff": None,
        }
        assert commit.report_json == {
            "files": {},
            "sessions": {},
            "totals": [0, 0, 0, 0, 0, None, 0, 0, 0, 0, 0, 0, None],
        }
        assert res["url"] in mock_storage.storage["archive"]
        assert mock_storage.storage["archive"][res["url"]] == b""

    def test_save_report(self, dbsession, mock_storage, sample_report):
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        current_report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(current_report_row)
        dbsession.flush()
        report_service = ReportService({})
        res = report_service.save_report(commit, sample_report)
        storage_hash = ArchiveService(commit.repository).storage_hash

        assert res == {
            "url": f"v4/repos/{storage_hash}/commits/{commit.commitid}/chunks.txt"
        }
        assert len(current_report_row.uploads) == 0
        assert commit.report_json == {
            "files": {
                "file_1.go": [
                    0,
                    [0, 8, 5, 3, 0, "62.50000", 0, 0, 0, 0, 10, 2, 0],
                    None,
                    None,
                ],
                "file_2.py": [
                    1,
                    [0, 2, 1, 0, 1, "50.00000", 1, 0, 0, 0, 0, 0, 0],
                    None,
                    None,
                ],
            },
            "sessions": {
                "0": {
                    "t": [2, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    "d": None,
                    "a": None,
                    "f": ["unit"],
                    "c": "circleci",
                    "n": "aycaramba",
                    "N": None,
                    "j": None,
                    "u": None,
                    "p": None,
                    "e": None,
                    "st": "uploaded",
                    "se": {},
                },
                "1": {
                    "t": None,
                    "d": None,
                    "a": None,
                    "f": ["integration"],
                    "c": "travis",
                    "n": "poli",
                    "N": None,
                    "j": None,
                    "u": None,
                    "p": None,
                    "e": None,
                    "st": "carriedforward",
                    "se": {},
                },
            },
            "totals": [2, 10, 6, 3, 1, "60.00000", 1, 0, 0, 2, 10, 2, None],
        }
        assert res["url"] in mock_storage.storage["archive"]
        expected_content = "\n".join(
            [
                '{"present_sessions":[0,1]}',
                "[1,null,[[0,1]],null,[10,2]]",
                "[0,null,[[0,1]]]",
                "[1,null,[[0,1]]]",
                "",
                "[1,null,[[0,1],[1,1]]]",
                "[0,null,[[0,1]]]",
                "",
                "[1,null,[[0,1],[1,0]]]",
                "[1,null,[[0,1]]]",
                "[0,null,[[0,1]]]",
                "<<<<< end_of_chunk >>>>>",
                '{"present_sessions":[0]}',
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "[1,null,[[0,1]]]",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                '["1/2","b",[[0,1]]]',
            ]
        )
        assert mock_storage.storage["archive"][res["url"]].decode() == expected_content

    def test_initialize_and_save_report_brand_new(self, dbsession, mock_storage):
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        report_service = ReportService({})
        r = report_service.initialize_and_save_report(commit)
        assert r is not None
        assert len(mock_storage.storage["archive"]) == 0

    def test_initialize_and_save_report_report_but_no_details(
        self, dbsession, mock_storage
    ):
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(report_row)
        dbsession.flush()
        report_service = ReportService({})
        r = report_service.initialize_and_save_report(commit)
        dbsession.refresh(report_row)
        assert r is not None
        assert len(mock_storage.storage["archive"]) == 0

    @pytest.mark.django_db
    def test_initialize_and_save_report_carryforward_needed(
        self, dbsession, sample_commit_with_report_big, mock_storage
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            _report_json=None,
            parent_commit_id=parent_commit.commitid,
            repository=parent_commit.repository,
        )
        dbsession.add(commit)
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        report_service = ReportService(UserYaml(yaml_dict))
        r = report_service.initialize_and_save_report(commit)
        assert len(r.uploads) == 2
        first_upload = dbsession.query(Upload).filter_by(
            report_id=r.id_, order_number=2
        )[0]
        second_upload = dbsession.query(Upload).filter_by(
            report_id=r.id_, order_number=3
        )[0]
        assert first_upload.build_code is None
        assert first_upload.build_url is None
        assert first_upload.env is None
        assert first_upload.job_code is None
        assert first_upload.name == "Carriedforward"
        assert first_upload.provider is None
        assert first_upload.report_id == r.id_
        assert first_upload.state == "complete"
        assert first_upload.storage_path == ""
        assert first_upload.order_number == 2
        assert len(first_upload.flags) == 1
        assert first_upload.flags[0].repository == commit.repository
        assert first_upload.flags[0].flag_name == "enterprise"
        assert first_upload.totals is None
        assert first_upload.upload_extras == {
            "carriedforward_from": parent_commit.commitid
        }
        assert first_upload.upload_type == "carriedforward"
        assert second_upload.build_code is None
        assert second_upload.build_url is None
        assert second_upload.env is None
        assert second_upload.job_code is None
        assert second_upload.name == "Carriedforward"
        assert second_upload.provider is None
        assert second_upload.report_id == r.id_
        assert second_upload.state == "complete"
        assert second_upload.storage_path == ""
        assert second_upload.order_number == 3
        assert len(second_upload.flags) == 2
        assert sorted([f.flag_name for f in second_upload.flags]) == [
            "enterprise",
            "unit",
        ]
        assert second_upload.totals is None
        assert second_upload.upload_extras == {
            "carriedforward_from": parent_commit.commitid
        }
        assert second_upload.upload_type == "carriedforward"

    @pytest.mark.django_db
    def test_initialize_and_save_report_report_but_no_details_carryforward_needed(
        self, dbsession, sample_commit_with_report_big, mock_storage
    ):
        parent_commit = sample_commit_with_report_big
        commit = CommitFactory.create(
            _report_json=None,
            parent_commit_id=parent_commit.commitid,
            repository=parent_commit.repository,
        )
        dbsession.add(commit)
        dbsession.flush()
        report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(report_row)
        dbsession.flush()
        yaml_dict = {"flags": {"enterprise": {"carryforward": True}}}
        report_service = ReportService(UserYaml(yaml_dict))
        r = report_service.initialize_and_save_report(commit)
        assert len(r.uploads) == 2
        first_upload = dbsession.query(Upload).filter_by(
            report_id=r.id_, order_number=2
        )[0]
        second_upload = dbsession.query(Upload).filter_by(
            report_id=r.id_, order_number=3
        )[0]
        assert first_upload.build_code is None
        assert first_upload.build_url is None
        assert first_upload.env is None
        assert first_upload.job_code is None
        assert first_upload.name == "Carriedforward"
        assert first_upload.provider is None
        assert first_upload.report_id == r.id_
        assert first_upload.state == "complete"
        assert first_upload.storage_path == ""
        assert first_upload.order_number == 2
        assert len(first_upload.flags) == 1
        assert first_upload.flags[0].repository == commit.repository
        assert first_upload.flags[0].flag_name == "enterprise"
        assert first_upload.totals is None
        assert first_upload.upload_extras == {
            "carriedforward_from": parent_commit.commitid
        }
        assert first_upload.upload_type == "carriedforward"
        assert second_upload.build_code is None
        assert second_upload.build_url is None
        assert second_upload.env is None
        assert second_upload.job_code is None
        assert second_upload.name == "Carriedforward"
        assert second_upload.provider is None
        assert second_upload.report_id == r.id_
        assert second_upload.state == "complete"
        assert second_upload.storage_path == ""
        assert second_upload.order_number == 3
        assert len(second_upload.flags) == 2
        assert sorted([f.flag_name for f in second_upload.flags]) == [
            "enterprise",
            "unit",
        ]
        assert second_upload.totals is None
        assert second_upload.upload_extras == {
            "carriedforward_from": parent_commit.commitid
        }
        assert second_upload.upload_type == "carriedforward"

    def test_initialize_and_save_report_needs_backporting(
        self, dbsession, sample_commit_with_report_big, mock_storage, mocker
    ):
        commit = sample_commit_with_report_big
        report_service = ReportService({})
        r = report_service.initialize_and_save_report(commit)
        assert r is not None
        assert len(r.uploads) == 4
        first_upload = dbsession.query(Upload).filter_by(order_number=0).first()
        assert sorted([f.flag_name for f in first_upload.flags]) == []
        second_upload = dbsession.query(Upload).filter_by(order_number=1).first()
        assert sorted([f.flag_name for f in second_upload.flags]) == ["unit"]
        third_upload = dbsession.query(Upload).filter_by(order_number=2).first()
        assert sorted([f.flag_name for f in third_upload.flags]) == ["enterprise"]
        fourth_upload = dbsession.query(Upload).filter_by(order_number=3).first()
        assert sorted([f.flag_name for f in fourth_upload.flags]) == [
            "enterprise",
            "unit",
        ]
        assert (
            dbsession.query(RepositoryFlag)
            .filter_by(repository_id=commit.repoid)
            .count()
            == 2
        )
        storage_keys = mock_storage.storage["archive"].keys()
        assert any(key.endswith("chunks.txt") for key in storage_keys)

    def test_initialize_and_save_report_existing_report(
        self, mock_storage, sample_report, dbsession, mocker
    ):
        mocker_save_full_report = mocker.patch.object(ReportService, "save_full_report")
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        current_report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(current_report_row)
        dbsession.flush()
        report_service = ReportService({})
        report_service.save_report(commit, sample_report)
        res = report_service.initialize_and_save_report(commit)
        assert res == current_report_row
        assert not mocker_save_full_report.called

    @pytest.mark.django_db
    def test_create_report_upload(self, dbsession):
        arguments = {
            "branch": "master",
            "build": "646048900",
            "build_url": "http://github.com/greenlantern/reponame/actions/runs/646048900",
            "cmd_args": "n,F,Q,C",
            "commit": "1280bf4b8d596f41b101ac425758226c021876da",
            "job": "thisjob",
            "flags": ["unittest"],
            "name": "this name contains more than 100 chars 1111111111111111111111111111111111111111111111111111111111111this is more than 100",
            "owner": "greenlantern",
            "package": "github-action-20210309-2b87ace",
            "pr": "33",
            "repo": "reponame",
            "reportid": "6e2b6449-4e60-43f8-80ae-2c03a5c03d92",
            "service": "github-actions",
            "slug": "greenlantern/reponame",
            "url": "v4/raw/2021-03-12/C00AE6C87E34AF41A6D38D154C609782/1280bf4b8d596f41b101ac425758226c021876da/6e2b6449-4e60-43f8-80ae-2c03a5c03d92.txt",
            "using_global_token": "false",
            "version": "v4",
        }
        commit = CommitFactory.create()
        dbsession.add(commit)
        dbsession.flush()
        current_report_row = CommitReport(commit_id=commit.id_)
        dbsession.add(current_report_row)
        dbsession.flush()
        report_service = ReportService({})
        res = report_service.create_report_upload(arguments, current_report_row)
        dbsession.flush()
        assert res.build_code == "646048900"
        assert (
            res.build_url
            == "http://github.com/greenlantern/reponame/actions/runs/646048900"
        )
        assert res.env is None
        assert res.job_code == "thisjob"
        assert (
            res.name
            == "this name contains more than 100 chars 1111111111111111111111111111111111111111111111111111111111111"
        )
        assert res.provider == "github-actions"
        assert res.report_id == current_report_row.id_
        assert res.state == "started"
        assert (
            res.storage_path
            == "v4/raw/2021-03-12/C00AE6C87E34AF41A6D38D154C609782/1280bf4b8d596f41b101ac425758226c021876da/6e2b6449-4e60-43f8-80ae-2c03a5c03d92.txt"
        )
        assert res.order_number is None
        assert res.totals is None
        assert res.upload_extras == {}
        assert res.upload_type == "uploaded"

    def test_shift_carryforward_report(
        self, dbsession, sample_report, mocker, mock_repo_provider
    ):
        parent_commit = CommitFactory()
        commit = CommitFactory(parent_commit_id=parent_commit.commitid)
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        fake_diff = {
            "diff": {
                "files": {
                    "file_1.go": {
                        "type": "modified",
                        "before": None,
                        "segments": [
                            {
                                "header": [3, 3, 3, 4],
                                "lines": [
                                    " some go code in line 3",
                                    "-this line was removed",
                                    "+this line was added",
                                    "+this line was also added",
                                    " ",
                                ],
                            },
                            {
                                "header": [9, 1, 10, 5],
                                "lines": [
                                    " some go code in line 9",
                                    "+add",
                                    "+add",
                                    "+add",
                                    "+add",
                                ],
                            },
                        ],
                    }
                }
            }
        }

        def fake_get_compare(base, head):
            assert base == parent_commit.commitid
            assert head == commit.commitid
            return fake_diff

        mock_repo_provider.get_compare = mock.AsyncMock(side_effect=fake_get_compare)
        result = ReportService({})._possibly_shift_carryforward_report(
            sample_report, parent_commit, commit
        )
        readable_report = convert_report_to_better_readable(result)
        assert readable_report["archive"] == {
            "file_1.go": [
                (1, 1, None, [[0, 1]], None, (10, 2)),
                (2, 0, None, [[0, 1]], None, None),
                (3, 1, None, [[0, 1]], None, None),
                (6, 1, None, [[0, 1], [1, 1]], None, None),
                (7, 0, None, [[0, 1]], None, None),
                (9, 1, None, [[0, 1], [1, 0]], None, None),
                (10, 1, None, [[0, 1]], None, None),
                (15, 0, None, [[0, 1]], None, None),
            ],
            "file_2.py": [
                (12, 1, None, [[0, 1]], None, None),
                (51, "1/2", "b", [[0, 1]], None, None),
            ],
        }

    @pytest.mark.django_db(databases={"default", "timeseries"})
    def test_create_new_report_for_commit_and_shift(
        self, dbsession, sample_report, mocker, mock_repo_provider, mock_storage
    ):
        parent_commit = CommitFactory()
        parent_commit_report = CommitReport(commit_id=parent_commit.id_)
        dbsession.add(parent_commit)
        dbsession.add(parent_commit_report)
        dbsession.flush()

        commit = CommitFactory.create(
            repository=parent_commit.repository,
            parent_commit_id=parent_commit.commitid,
            _report_json=None,
        )
        dbsession.add(commit)
        dbsession.flush()
        dbsession.add(CommitReport(commit_id=commit.id_))
        dbsession.flush()
        yaml_dict = {
            "flags": {
                "integration": {"carryforward": True},
                "unit": {"carryforward": True},
            }
        }

        fake_diff = {
            "diff": {
                "files": {
                    "file_1.go": {
                        "type": "modified",
                        "before": None,
                        "segments": [
                            {
                                "header": [3, 3, 3, 4],
                                "lines": [
                                    " some go code in line 3",
                                    "-this line was removed",
                                    "+this line was added",
                                    "+this line was also added",
                                    " ",
                                ],
                            },
                            {
                                "header": [9, 1, 10, 5],
                                "lines": [
                                    " some go code in line 9",
                                    "+add",
                                    "+add",
                                    "+add",
                                    "+add",
                                ],
                            },
                        ],
                    }
                }
            }
        }

        def fake_get_compare(base, head):
            assert base == parent_commit.commitid
            assert head == commit.commitid
            return fake_diff

        mock_repo_provider.get_compare = mock.AsyncMock(side_effect=fake_get_compare)

        mock_get_report = mocker.patch.object(
            ReportService, "get_existing_report_for_commit", return_value=sample_report
        )

        result = ReportService(UserYaml(yaml_dict)).create_new_report_for_commit(commit)
        assert mock_get_report.call_count == 1
        readable_report = convert_report_to_better_readable(result)
        assert readable_report["archive"] == {
            "file_1.go": [
                (1, 1, None, [[0, 1]], None, (10, 2)),
                (2, 0, None, [[0, 1]], None, None),
                (3, 1, None, [[0, 1]], None, None),
                (6, 1, None, [[0, 1], [1, 1]], None, None),
                (7, 0, None, [[0, 1]], None, None),
                (9, 1, None, [[0, 1], [1, 0]], None, None),
                (10, 1, None, [[0, 1]], None, None),
                (15, 0, None, [[0, 1]], None, None),
            ],
            "file_2.py": [
                (12, 1, None, [[0, 1]], None, None),
                (51, "1/2", "b", [[0, 1]], None, None),
            ],
        }

    def test_possibly_shift_carryforward_report_cant_get_diff(
        self, dbsession, sample_report, mocker
    ):
        parent_commit = CommitFactory()
        commit = CommitFactory(parent_commit_id=parent_commit.commitid)
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        mock_log_error = mocker.patch.object(report_log, "error")

        def raise_error(*args, **kwargs):
            raise TorngitRateLimitError(response_data="", message="error", reset=None)

        fake_provider = mocker.Mock()
        fake_provider.get_compare = raise_error
        mock_provider_service = mocker.patch(
            "services.report.get_repo_provider_service", return_value=fake_provider
        )
        result = ReportService({})._possibly_shift_carryforward_report(
            sample_report, parent_commit, commit
        )
        assert result == sample_report
        mock_provider_service.assert_called()
        mock_log_error.assert_called_with(
            "Failed to shift carryforward report lines.",
            extra={
                "reason": "Can't get diff",
                "commit": commit.commitid,
                "error": str(
                    TorngitRateLimitError(response_data="", message="error", reset=None)
                ),
                "error_type": type(
                    TorngitRateLimitError(response_data="", message="error", reset=None)
                ),
            },
        )

    def test_possibly_shift_carryforward_report_bot_error(
        self, dbsession, sample_report, mocker
    ):
        parent_commit = CommitFactory()
        commit = CommitFactory(parent_commit_id=parent_commit.commitid)
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        mock_log_error = mocker.patch.object(report_log, "error")

        def raise_error(*args, **kwargs):
            raise RepositoryWithoutValidBotError()

        mock_provider_service = mocker.patch(
            "services.report.get_repo_provider_service", side_effect=raise_error
        )
        result = ReportService({})._possibly_shift_carryforward_report(
            sample_report, parent_commit, commit
        )
        assert result == sample_report
        mock_provider_service.assert_called()
        mock_log_error.assert_called_with(
            "Failed to shift carryforward report lines",
            extra={
                "reason": "Can't get provider_service",
                "commit": commit.commitid,
                "error": str(RepositoryWithoutValidBotError()),
            },
        )

    def test_possibly_shift_carryforward_report_random_processing_error(
        self, dbsession, mocker, mock_repo_provider
    ):
        parent_commit = CommitFactory()
        commit = CommitFactory(parent_commit_id=parent_commit.commitid)
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()
        mock_log_error = mocker.patch.object(report_log, "error")

        def raise_error(*args, **kwargs):
            raise Exception("Very random and hard to get exception")

        mock_repo_provider.get_compare = mock.AsyncMock(
            side_effect=lambda *args, **kwargs: {"diff": {}}
        )
        mock_report = mocker.Mock()
        mock_report.shift_lines_by_diff = raise_error
        result = ReportService({})._possibly_shift_carryforward_report(
            mock_report, parent_commit, commit
        )
        assert result == mock_report
        mock_log_error.assert_called_with(
            "Failed to shift carryforward report lines.",
            exc_info=True,
            extra={
                "reason": "Unknown",
                "commit": commit.commitid,
            },
        )

    def test_possibly_shift_carryforward_report_softtimelimit_reraised(
        self, dbsession, mocker, mock_repo_provider
    ):
        parent_commit = CommitFactory()
        commit = CommitFactory(parent_commit_id=parent_commit.commitid)
        dbsession.add(parent_commit)
        dbsession.add(commit)
        dbsession.flush()

        def raise_error(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        mock_report = mocker.Mock()
        mock_report.shift_lines_by_diff = raise_error
        with pytest.raises(SoftTimeLimitExceeded):
            ReportService({})._possibly_shift_carryforward_report(
                mock_report, parent_commit, commit
            )
