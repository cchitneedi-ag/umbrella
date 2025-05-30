from services.report.languages import xcode
from shared.reports.test_utils import convert_report_to_better_readable

from . import create_report_builder_session

txt = b"""/source:
      1|    |line
      2|   1|line
  ------------------
  | -[UVWelcomeViewController dealloc]:
  |      0|  360|        noErr                   OSErr: function performed properly - no error
  ------------------
      3|   0|line

/totally_empty:
/file:
    1|   |line
    2|   1k|line
           warning: The file '/Users/Jack/Documents/Coupgon/sdk-ios/Source/CPGCoupgonsViewController.swift' isn't covered.
    \033\x1b[0;36m/file:\033[0m
    3|   1m|line
    4|   1|   }

/ignore:
    1|   0|line
"""


class TestXcode2:
    def test_report(self):
        def fixes(path):
            if path == "ignore":
                return None
            assert path in ("source", "file", "empty", "totally_empty")
            return path

        report_builder_session = create_report_builder_session(path_fixer=fixes)
        xcode.from_txt(txt, report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        expected_result_archive = {
            "file": [
                (2, 1000, None, [[0, 1000]], None, None),
                (3, 99999, None, [[0, 99999]], None, None),
            ],
            "source": [
                (2, 1, None, [[0, 1]], None, None),
                (3, 0, None, [[0, 0]], None, None),
            ],
        }

        assert expected_result_archive == processed_report["archive"]

    def test_removes_last(self):
        report_builder_session = create_report_builder_session()
        xcode.from_txt(
            b"""\nnothing\n/file:\n    1 |   1|line\n/totally_empty:""",
            report_builder_session,
        )
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert "totally_empty" not in processed_report["archive"]
        assert "file" in processed_report["archive"]
