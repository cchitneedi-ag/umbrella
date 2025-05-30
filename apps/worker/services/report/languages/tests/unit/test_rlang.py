from services.report.languages import rlang
from shared.reports.test_utils import convert_report_to_better_readable

from . import create_report_builder_session

json = {
    "uploader": "R",
    "files": [
        {"name": "source/cov.r", "coverage": [None, 1, 0]},
        {"name": "source/app.r", "coverage": [None, 1]},
    ],
}


class TestRlang:
    def test_report(self):
        def fixes(path):
            assert path in ("source/cov.r", "source/app.r")
            return path

        report_builder_session = create_report_builder_session(path_fixer=fixes)
        rlang.from_json(json, report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert processed_report["archive"] == {
            "source/app.r": [(1, 1, None, [[0, 1]], None, None)],
            "source/cov.r": [
                (1, 1, None, [[0, 1]], None, None),
                (2, 0, None, [[0, 0]], None, None),
            ],
        }
