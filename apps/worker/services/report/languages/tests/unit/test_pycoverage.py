"""Tests for pycoverage language processor that output actual labels.
This is going to be deprecated soon.
For the tests with encoded labels see services/report/languages/tests/unit/test_pycoverage_encoded_labels.py
"""

from services.report.languages.pycoverage import PyCoverageProcessor
from shared.reports.test_utils import convert_report_to_better_readable

from . import create_report_builder_session

SAMPLE = {
    "meta": {
        "version": "6.4.1",
        "timestamp": "2022-06-27T01:44:41.238230",
        "branch_coverage": False,
        "show_contexts": True,
    },
    "files": {
        "another.py": {
            "executed_lines": [1, 2, 3, 4],
            "summary": {
                "covered_lines": 4,
                "num_statements": 4,
                "percent_covered": 100.0,
                "percent_covered_display": "100",
                "missing_lines": 0,
                "excluded_lines": 0,
            },
            "missing_lines": [],
            "excluded_lines": [],
            "contexts": {
                "1": [""],
                "2": [
                    "test_another.py::test_fib_simple_case|run",
                    "test_another.py::test_fib_bigger_cases|run",
                ],
                "3": [
                    "test_another.py::test_fib_simple_case|run",
                    "test_another.py::test_fib_bigger_cases|run",
                ],
                "4": ["test_another.py::test_fib_bigger_cases|run"],
            },
        },
        "source.py": {
            "executed_lines": [1, 3, 4, 5, 9],
            "summary": {
                "covered_lines": 5,
                "num_statements": 7,
                "percent_covered": 71.42857142857143,
                "percent_covered_display": "71",
                "missing_lines": 2,
                "excluded_lines": 0,
            },
            "missing_lines": [6, 10],
            "excluded_lines": [],
            "contexts": {
                "1": [""],
                "3": [""],
                "9": [""],
                "4": ["test_source.py::test_some_code|run"],
                "5": ["test_source.py::test_some_code|run"],
            },
        },
        "test_another.py": {
            "executed_lines": [1, 3, 4, 5, 7, 8],
            "summary": {
                "covered_lines": 6,
                "num_statements": 6,
                "percent_covered": 100.0,
                "percent_covered_display": "100",
                "missing_lines": 0,
                "excluded_lines": 0,
            },
            "missing_lines": [],
            "excluded_lines": [],
            "contexts": {
                "1": [""],
                "3": [""],
                "7": [""],
                "4": ["test_another.py::test_fib_simple_case|run"],
                "5": ["test_another.py::test_fib_simple_case|run"],
                "8": ["test_another.py::test_fib_bigger_cases|run"],
            },
        },
        "test_source.py": {
            "executed_lines": [1, 4, 5],
            "summary": {
                "covered_lines": 3,
                "num_statements": 3,
                "percent_covered": 100.0,
                "percent_covered_display": "100",
                "missing_lines": 0,
                "excluded_lines": 0,
            },
            "missing_lines": [],
            "excluded_lines": [],
            "contexts": {
                "1": [""],
                "4": [""],
                "5": ["test_source.py::test_some_code|run"],
            },
        },
    },
    "totals": {
        "covered_lines": 18,
        "num_statements": 20,
        "percent_covered": 90.0,
        "percent_covered_display": "90",
        "missing_lines": 2,
        "excluded_lines": 0,
    },
}

COMPRESSED_SAMPLE = {
    "meta": {
        "version": "6.5.0",
        "timestamp": "2023-05-15T18:35:30.641570",
        "branch_coverage": False,
        "show_contexts": True,
    },
    "totals": {
        "covered_lines": 4,
        "num_statements": 9,
        "percent_covered": "44.44444",
        "percent_covered_display": "44",
        "missing_lines": 5,
        "excluded_lines": 0,
    },
    "files": {
        "awesome.py": {
            "executed_lines": [1, 2, 3, 5],
            "summary": {
                "covered_lines": 4,
                "num_statements": 5,
                "percent_covered": "80.0",
                "percent_covered_display": "80",
                "missing_lines": 1,
                "excluded_lines": 0,
            },
            "missing_lines": [4],
            "excluded_lines": [],
            "contexts": {
                "1": [0],
                "2": [1, 2],
                "3": [2, 3],
                "5": [4],
            },
        },
        "__init__.py": {
            "executed_lines": [],
            "summary": {
                "covered_lines": 0,
                "num_statements": 4,
                "percent_covered": "0.0",
                "percent_covered_display": "0",
                "missing_lines": 4,
                "excluded_lines": 0,
            },
            "missing_lines": [1, 3, 4, 5],
            "excluded_lines": [],
            "contexts": {},
        },
        "services/__init__.py": {
            "executed_lines": [0],
            "summary": {
                "covered_lines": 0,
                "num_statements": 0,
                "percent_covered": "100.0",
                "percent_covered_display": "100",
                "missing_lines": 0,
                "excluded_lines": 0,
            },
            "missing_lines": [],
            "excluded_lines": [],
            "contexts": {"0": [0]},
        },
    },
    "labels_table": {
        "0": "",
        "1": "label_1",
        "2": "label_2",
        "3": "label_3",
        "4": "label_5",
    },
}


class TestPyCoverageProcessor:
    def test_matches_content_pycoverage(self):
        p = PyCoverageProcessor()
        assert p.matches_content(SAMPLE, "", "coverage.json")
        assert not p.matches_content({"meta": True}, "", "coverage.json")
        assert not p.matches_content({"meta": {}}, "", "coverage.json")

    def test_process_pycoverage(self):
        content = SAMPLE
        p = PyCoverageProcessor()
        report_builder_session = create_report_builder_session(
            current_yaml={
                "flag_management": {
                    "default_rules": {
                        "carryforward": "true",
                        "carryforward_mode": "labels",
                    }
                }
            },
        )
        p.process(content, report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert processed_report == {
            "archive": {
                "another.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (2, 1, None, [[0, 1]], None, None),
                    (3, 1, None, [[0, 1]], None, None),
                    (4, 1, None, [[0, 1]], None, None),
                ],
                "source.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (3, 1, None, [[0, 1]], None, None),
                    (4, 1, None, [[0, 1]], None, None),
                    (5, 1, None, [[0, 1]], None, None),
                    (6, 0, None, [[0, 0]], None, None),
                    (9, 1, None, [[0, 1]], None, None),
                    (10, 0, None, [[0, 0]], None, None),
                ],
                "test_another.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (3, 1, None, [[0, 1]], None, None),
                    (4, 1, None, [[0, 1]], None, None),
                    (5, 1, None, [[0, 1]], None, None),
                    (7, 1, None, [[0, 1]], None, None),
                    (8, 1, None, [[0, 1]], None, None),
                ],
                "test_source.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (4, 1, None, [[0, 1]], None, None),
                    (5, 1, None, [[0, 1]], None, None),
                ],
            },
            "report": {
                "files": {
                    "another.py": [
                        0,
                        [0, 4, 4, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "source.py": [
                        1,
                        [0, 7, 5, 2, 0, "71.42857", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "test_another.py": [
                        2,
                        [0, 6, 6, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "test_source.py": [
                        3,
                        [0, 3, 3, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {},
            },
            "totals": {
                "f": 4,
                "n": 20,
                "h": 18,
                "m": 2,
                "p": 0,
                "c": "90.00000",
                "b": 0,
                "d": 0,
                "M": 0,
                "s": 0,
                "C": 0,
                "N": 0,
                "diff": None,
            },
        }

    def test_process_compressed_report(self):
        content = COMPRESSED_SAMPLE
        p = PyCoverageProcessor()
        report_builder_session = create_report_builder_session(
            current_yaml={
                "flag_management": {
                    "default_rules": {
                        "carryforward": "true",
                        "carryforward_mode": "labels",
                    }
                }
            },
        )
        p.process(content, report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert processed_report == {
            "archive": {
                "awesome.py": [
                    (1, 1, None, [[0, 1]], None, None),
                    (2, 1, None, [[0, 1]], None, None),
                    (3, 1, None, [[0, 1]], None, None),
                    (4, 0, None, [[0, 0]], None, None),
                    (5, 1, None, [[0, 1]], None, None),
                ],
                "__init__.py": [
                    (1, 0, None, [[0, 0]], None, None),
                    (3, 0, None, [[0, 0]], None, None),
                    (4, 0, None, [[0, 0]], None, None),
                    (5, 0, None, [[0, 0]], None, None),
                ],
            },
            "report": {
                "files": {
                    "awesome.py": [
                        0,
                        [0, 5, 4, 1, 0, "80.00000", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "__init__.py": [
                        1,
                        [0, 4, 0, 4, 0, "0", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {},
            },
            "totals": {
                "f": 2,
                "n": 9,
                "h": 4,
                "m": 5,
                "p": 0,
                "c": "44.44444",
                "b": 0,
                "d": 0,
                "M": 0,
                "s": 0,
                "C": 0,
                "N": 0,
                "diff": None,
            },
        }
