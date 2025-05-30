import pytest

from shared.reports.editable import EditableReport, EditableReportFile
from shared.reports.resources import Report, ReportFile
from shared.reports.serde import _encode_chunk
from shared.reports.types import ReportLine, ReportTotals
from shared.utils.sessions import Session


def report_with_file_summaries():
    return Report(
        files={
            "calc/CalcCore.cpp": [
                0,
                ReportTotals(
                    files=0,
                    lines=10,
                    hits=7,
                    misses=2,
                    partials=1,
                    coverage="70.00000",
                    branches=6,
                    methods=4,
                    messages=0,
                    sessions=0,
                    complexity=0,
                    complexity_total=0,
                    diff=0,
                ),
            ],
            "calc/CalcCore.h": [
                1,
                ReportTotals(
                    files=0,
                    lines=1,
                    hits=1,
                    misses=0,
                    partials=0,
                    coverage="100",
                    branches=0,
                    methods=1,
                    messages=0,
                    sessions=0,
                    complexity=0,
                    complexity_total=0,
                    diff=0,
                ),
            ],
            "calc/Calculator.cpp": [
                2,
                ReportTotals(
                    files=0,
                    lines=4,
                    hits=3,
                    misses=1,
                    partials=0,
                    coverage="75.00000",
                    branches=1,
                    methods=1,
                    messages=0,
                    sessions=0,
                    complexity=0,
                    complexity_total=0,
                    diff=0,
                ),
            ],
        },
        totals=ReportTotals(
            files=3,
            lines=15,
            hits=11,
            misses=3,
            partials=1,
            coverage="73.33333",
            branches=7,
            methods=6,
            messages=0,
            sessions=0,
            complexity=0,
            complexity_total=0,
            diff=0,
        ),
    )


def test_files():
    r = Report(files={"py.py": [0, ReportTotals(1)]})
    assert r.files == ["py.py"]


@pytest.mark.unit
def test_get_file_totals(mocker):
    report = report_with_file_summaries()

    expected_totals = ReportTotals(
        files=0,
        lines=10,
        hits=7,
        misses=2,
        partials=1,
        coverage="70.00000",
        branches=6,
        methods=4,
        messages=0,
        sessions=0,
        complexity=0,
        complexity_total=0,
        diff=0,
    )
    assert report.get_file_totals("calc/CalcCore.cpp") == expected_totals


@pytest.mark.unit
def test_merge_into_editable_report():
    editable_report = EditableReport(
        files={"file.py": [1, ReportTotals(2)]},
        chunks="null\n[1]\n[1]\n[1]\n<<<<< end_of_chunk >>>>>\nnull\n[1]\n[1]\n[1]",
    )
    new_report = Report(
        files={"other-file.py": [1, ReportTotals(2)]},
        chunks="null\n[1]\n[1]\n[1]\n<<<<< end_of_chunk >>>>>\nnull\n[1]\n[1]\n[1]",
    )
    editable_report.merge(new_report)
    assert list(editable_report.files) == ["file.py", "other-file.py"]
    for file in editable_report:
        assert isinstance(file, EditableReportFile)


@pytest.mark.unit
def test_calculate_diff():
    v3 = {
        "files": {"a": [0, None], "d": [1, None]},
        "sessions": {},
        "totals": {},
        "chunks": [
            "\n[1, null, null, null]\n[0, null, null, null]",
            "\n[1, null, null, null]\n[0, null, null, null]",
        ],
    }
    r = Report(**v3)
    diff = {
        "files": {
            "a": {
                "type": "new",
                "segments": [{"header": list("1313"), "lines": list("---+++")}],
            },
            "b": {"type": "deleted"},
            "c": {"type": "modified"},
            "d": {
                "type": "modified",
                "segments": [
                    {"header": ["10", "3", "10", "3"], "lines": list("---+++")}
                ],
            },
        }
    }
    res = r.calculate_diff(diff)
    expected_result = {
        "files": {
            "a": ReportTotals(
                files=0, lines=2, hits=1, misses=1, partials=0, coverage="50.00000"
            ),
            "d": ReportTotals(
                files=0, lines=0, hits=0, misses=0, partials=0, coverage=None
            ),
        },
        "general": ReportTotals(
            files=2,
            lines=2,
            hits=1,
            misses=1,
            partials=0,
            coverage="50.00000",
            branches=0,
            methods=0,
            messages=0,
            sessions=0,
            complexity=0,
            complexity_total=0,
            diff=0,
        ),
    }
    assert res["files"] == expected_result["files"]
    assert res == expected_result


@pytest.mark.unit
def test_apply_diff_no_diff():
    v3 = {
        "files": {"a": [0, None], "d": [1, None]},
        "sessions": {},
        "totals": {},
        "chunks": [
            "\n[1, null, null, null]\n[0, null, null, null]",
            "\n[1, null, null, null]\n[0, null, null, null]",
        ],
    }
    r = Report(**v3)
    diff = {"files": {}}
    res = r.apply_diff(diff)
    assert res is None
    assert diff == {"files": {}}


@pytest.mark.unit
def test_encode_chunk():
    assert _encode_chunk(None) == "null"
    assert _encode_chunk(ReportFile(name="name.ply")) == '{"present_sessions":[]}\n'
    assert (
        _encode_chunk([ReportLine.create(2), ReportLine.create(1)])
        == "[[2,null,null,null,null],[1,null,null,null,null]]"
    )


@pytest.mark.unit
def test_delete_session():
    chunks = "\n".join(
        [
            "{}",
            "[1, null, [[0, 1], [1, 0]]]",
            "",
            "",
            "[0, null, [[0, 0], [1, 0]]]",
            "[1, null, [[0, 1], [1, 1]]]",
            "[1, null, [[0, 0], [1, 1]]]",
            "",
            "",
            '[1, null, [[0, 1], [1, "1/2"]]]',
            '[1, null, [[0, "1/2"], [1, 1]]]',
            "",
            "",
            "[1, null, [[0, 1]]]",
            "[1, null, [[1, 1]]]",
            '["1/2", null, [[0, "1/2"], [1, 0]]]',
            '["1/2", null, [[0, 0], [1, "1/2"]]]',
        ]
    )
    report_file = EditableReportFile(name="file.py", lines=chunks)
    assert report_file.totals == ReportTotals(
        files=0,
        lines=10,
        hits=7,
        misses=1,
        partials=2,
        coverage="70.00000",
        branches=0,
        methods=0,
        messages=0,
        sessions=0,
        complexity=0,
        complexity_total=0,
        diff=0,
    )
    report_file.delete_multiple_sessions({1})
    expected_result = [
        (1, ReportLine.create(1, sessions=[(0, 1)])),
        (4, ReportLine.create(0, sessions=[(0, 0)])),
        (5, ReportLine.create(1, sessions=[(0, 1)])),
        (6, ReportLine.create(0, sessions=[(0, 0)])),
        (9, ReportLine.create(1, sessions=[(0, 1)])),
        (10, ReportLine.create("1/2", sessions=[(0, "1/2")])),
        (13, ReportLine.create(1, sessions=[(0, 1)])),
        (15, ReportLine.create("1/2", sessions=[(0, "1/2")])),
        (16, ReportLine.create(0, sessions=[(0, 0)])),
    ]
    assert list(report_file.lines) == expected_result
    assert report_file.get(1) == ReportLine.create(1, sessions=[(0, 1)])
    assert report_file.get(13) == ReportLine.create(1, sessions=[(0, 1)])
    assert report_file.get(14) is None
    assert report_file.totals == ReportTotals(
        files=0,
        lines=9,
        hits=4,
        misses=3,
        partials=2,
        coverage="44.44444",
        branches=0,
        methods=0,
        messages=0,
        sessions=0,
        complexity=0,
        complexity_total=0,
        diff=0,
    )


@pytest.mark.unit
def test_get_flag_names(sample_report):
    assert sample_report.get_flag_names() == ["complex", "simple"]


@pytest.mark.unit
def test_get_flag_names_no_sessions():
    assert Report().get_flag_names() == []


@pytest.mark.unit
def test_get_flag_names_sessions_no_flags():
    s = Session()
    r = Report()
    r.add_session(s)
    assert r.get_flag_names() == []


@pytest.mark.unit
def test_shift_lines_by_diff():
    r = ReportFile("filename", lines=[ReportLine.create(n) for n in range(8)])
    report = Report(sessions={0: Session()})
    report.append(r)
    assert list(r.lines) == [
        (1, ReportLine.create(0)),
        (2, ReportLine.create(1)),
        (3, ReportLine.create(2)),
        (4, ReportLine.create(3)),
        (5, ReportLine.create(4)),
        (6, ReportLine.create(5)),
        (7, ReportLine.create(6)),
        (8, ReportLine.create(7)),
    ]
    assert report.totals == ReportTotals(
        files=1,
        lines=8,
        hits=7,
        misses=1,
        partials=0,
        coverage="87.50000",
        branches=0,
        methods=0,
        messages=0,
        sessions=1,
        complexity=0,
        complexity_total=0,
        diff=0,
    )
    report.shift_lines_by_diff(
        {
            "files": {
                "filename": {
                    "type": "modified",
                    "segments": [
                        {
                            # [-, -, POS_to_start, new_lines_added]
                            "header": [1, 1, 1, 1],
                            "lines": ["- afefe", "+ fefe", "="],
                        },
                        {
                            # [-, -, POS_to_start, new_lines_added]
                            "header": [5, 3, 5, 2],
                            "lines": ["- ", "- ", "- ", "+ ", "+ ", " ="],
                        },
                    ],
                }
            }
        }
    )
    assert report.files == ["filename"]
    file = report.get("filename")
    assert list(file.lines) == [
        (2, ReportLine.create(1)),
        (3, ReportLine.create(2)),
        (4, ReportLine.create(3)),
        (7, ReportLine.create(7)),
    ]
    assert file.totals == ReportTotals(
        files=0,
        lines=4,
        hits=4,
        misses=0,
        partials=0,
        coverage="100",
        branches=0,
        methods=0,
        messages=0,
        sessions=0,
        complexity=0,
        complexity_total=0,
        diff=0,
    )
