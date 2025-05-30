import datetime
import xml.etree.ElementTree as etree
from time import time

import pytest

from helpers.exceptions import ReportExpiredException
from services.report.languages import clover
from shared.reports.test_utils import convert_report_to_better_readable

from . import create_report_builder_session

xml = """<?xml version="1.0" encoding="UTF-8"?>
<coverage generated="%s">
  <project timestamp="1410539625">
    <package name="Codecov">
      <file name="source.php">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="6" coveredstatements="2" elements="7" coveredelements="2"/>
        </class>
        <line num="5" type="method" name="send" crap="125.96" count="1"/>
        <line complexity="9" visibility="private" signature="findRepeatableAnnotations(AnnotatedElement,Class&lt;A&gt;,Set&lt;Annotation&gt;) : List&lt;A&gt;" num="6" count="2969" type="method"/>

        <line falsecount="0" truecount="1" num="1" type="cond"/>
        <line falsecount="1" truecount="0" num="2" type="cond"/>
        <line falsecount="1" truecount="1" num="3" type="cond"/>
        <line falsecount="0" truecount="0" num="4" type="cond"/>

        <line num="8" type="stmt" count="0"/>
        <line num="11" type="stmt" count="1"/>
        <line num="21" type="stmt" count="0"/>
        <line num="22" type="stmt" count="0"/>
        <line num="23" type="stmt" count="0"/>
        <line num="87" type="stmt" count="0"/>
        <metrics loc="86" ncloc="62" classes="1" methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="6" coveredstatements="2" elements="7" coveredelements="2"/>
      </file>
      <file path="file.php">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="0" coveredstatements="0" elements="0" coveredelements="0"/>
        </class>
        <line num="11" type="stmt" count="1"/>
      </file>
      <file name="nolines">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="0" coveredstatements="0" elements="0" coveredelements="0"/>
        </class>
      </file>
      <file name="ignore">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="0" coveredstatements="0" elements="0" coveredelements="0"/>
        </class>
        <line num="11" type="stmt" count="1"/>
      </file>
      <file name="vendor/ignoreme.php">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="0" coveredstatements="0" elements="0" coveredelements="0"/>
        </class>
      </file>
      <file name="/${1}.php">
        <class name="Coverage" namespace="Codecov">
          <metrics methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="0" coveredstatements="0" elements="0" coveredelements="0"/>
        </class>
      </file>
    </package>
    <metrics files="1" loc="86" ncloc="62" classes="1" methods="1" coveredmethods="0" conditionals="0" coveredconditionals="0" statements="6" coveredstatements="2" elements="7" coveredelements="2"/>
  </project>
</coverage>
"""


class TestCloverProcessor:
    def test_report(self):
        def fixes(path):
            if path == "ignore":
                return None
            assert path in ("source.php", "file.php", "nolines")
            return path

        report_builder_session = create_report_builder_session(path_fixer=fixes)
        clover.from_xml(etree.fromstring(xml % int(time())), report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert processed_report == {
            "archive": {
                "file.php": [(11, 1, None, [[0, 1]], None, None)],
                "source.php": [
                    (1, "1/2", "b", [[0, "1/2"]], None, None),
                    (2, "1/2", "b", [[0, "1/2"]], None, None),
                    (3, "2/2", "b", [[0, "2/2"]], None, None),
                    (4, "0/2", "b", [[0, "0/2"]], None, None),
                    (5, 1, "m", [[0, 1, None, None, 0]], None, 0),
                    (6, 2969, "m", [[0, 2969, None, None, 9]], None, 9),
                    (8, 0, None, [[0, 0]], None, None),
                    (11, 1, None, [[0, 1]], None, None),
                    (21, 0, None, [[0, 0]], None, None),
                    (22, 0, None, [[0, 0]], None, None),
                    (23, 0, None, [[0, 0]], None, None),
                ],
            },
            "report": {
                "files": {
                    "file.php": [
                        1,
                        [0, 1, 1, 0, 0, "100", 0, 0, 0, 0, 0, 0, 0],
                        None,
                        None,
                    ],
                    "source.php": [
                        0,
                        [0, 11, 4, 5, 2, "36.36364", 4, 2, 0, 0, 9, 0, 0],
                        None,
                        None,
                    ],
                },
                "sessions": {},
            },
            "totals": {
                "C": 9,
                "M": 0,
                "N": 0,
                "b": 4,
                "c": "41.66667",
                "d": 2,
                "diff": None,
                "f": 2,
                "h": 5,
                "m": 5,
                "n": 12,
                "p": 2,
                "s": 0,
            },
        }

    @pytest.mark.parametrize(
        "date",
        [
            (datetime.datetime.now() - datetime.timedelta(seconds=172800))
            .replace(minute=0, second=0)
            .strftime("%s"),
            "01-01-2014",
        ],
    )
    def test_expired(self, date):
        report_builder_session = create_report_builder_session()
        with pytest.raises(ReportExpiredException, match="Clover report expired"):
            clover.from_xml(etree.fromstring(xml % date), report_builder_session)
