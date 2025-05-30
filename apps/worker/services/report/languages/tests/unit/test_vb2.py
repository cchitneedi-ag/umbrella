import xml.etree.ElementTree as etree

from services.report.languages import vb2
from shared.reports.test_utils import convert_report_to_better_readable

from . import create_report_builder_session

txt = """<?xml version="1.0" standalone="yes"?>
<CoverageDSPriv>
  <Lines>
    <LnStart>258</LnStart>
    <ColStart>0</ColStart>
    <LnEnd>258</LnEnd>
    <ColEnd>0</ColEnd>
    <Coverage>1</Coverage>
    <SourceFileID>1</SourceFileID>
    <LineID>0</LineID>
  </Lines>
  <Lines>
    <LnStart>260</LnStart>
    <ColStart>0</ColStart>
    <LnEnd>260</LnEnd>
    <ColEnd>0</ColEnd>
    <Coverage>0</Coverage>
    <SourceFileID>5</SourceFileID>
    <LineID>1</LineID>
  </Lines>
  <Lines>
    <LnStart>261</LnStart>
    <ColStart>0</ColStart>
    <LnEnd>262</LnEnd>
    <ColEnd>0</ColEnd>
    <Coverage>2</Coverage>
    <SourceFileID>5</SourceFileID>
    <LineID>1</LineID>
  </Lines>
  <SourceFileNames>
    <SourceFileID>1</SourceFileID>
    <SourceFileName>source\\mobius\\cpp\\riosock\\riosock.cpp</SourceFileName>
  </SourceFileNames>
  <SourceFileNames>
    <SourceFileID>5</SourceFileID>
    <SourceFileName>Source\\Mobius\\csharp\\Tests.Common\\RowHelper.cs</SourceFileName>
  </SourceFileNames>
</CoverageDSPriv>
"""


class TestVBTwo:
    def test_report(self):
        report_builder_session = create_report_builder_session()
        report = vb2.from_xml(etree.fromstring(txt), report_builder_session)
        report = report_builder_session.output_report()
        processed_report = convert_report_to_better_readable(report)

        assert processed_report["archive"] == {
            "Source/Mobius/csharp/Tests.Common/RowHelper.cs": [
                (260, 1, None, [[0, 1]], None, None),
                (261, 0, None, [[0, 0]], None, None),
                (262, 0, None, [[0, 0]], None, None),
            ],
            "source/mobius/cpp/riosock/riosock.cpp": [
                (258, True, None, [[0, True]], None, None)
            ],
        }
