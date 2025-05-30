import logging
from collections.abc import Sequence
from enum import Enum
from typing import Any

from services.path_fixer import PathFixer
from services.yaml.reader import read_yaml_field
from shared.reports.reportfile import ReportFile
from shared.reports.resources import Report
from shared.reports.types import LineSession, ReportLine
from shared.yaml.user_yaml import UserYaml

log = logging.getLogger(__name__)


class CoverageType(Enum):
    line = ("line", None)
    branch = ("branch", "b")
    method = ("method", "m")

    def __init__(self, code, report_value):
        self.code = code
        self.report_value = report_value

    def map_to_string(self):
        return self.report_value


class ReportBuilderSession:
    def __init__(self, report_builder: "ReportBuilder", report_filepath: str):
        self.filepath = report_filepath
        self._report_builder = report_builder
        self._report = Report()

    @property
    def path_fixer(self):
        return self._report_builder.path_fixer

    def resolve_paths(self, paths):
        return self._report.resolve_paths(paths)

    def yaml_field(self, keys: Sequence[str], default: Any = None) -> Any:
        return read_yaml_field(self._report_builder.current_yaml, keys, default)

    def get_file(self, filename: str) -> ReportFile | None:
        return self._report.get(filename)

    def append(self, file: ReportFile):
        return self._report.append(file)

    def output_report(self) -> Report:
        return self._report

    def create_coverage_file(
        self, path: str, do_fix_path: bool = True
    ) -> ReportFile | None:
        fixed_path = self._report_builder.path_fixer(path) if do_fix_path else path
        if not fixed_path:
            return None

        return ReportFile(
            fixed_path, ignore=self._report_builder.ignored_lines.get(fixed_path)
        )

    def create_coverage_line(
        self,
        coverage: int | str,
        coverage_type: CoverageType | None = None,
        partials=None,
        missing_branches=None,
        complexity=None,
    ) -> ReportLine:
        sessionid = self._report_builder.sessionid
        coverage_type_str = coverage_type.map_to_string() if coverage_type else None
        return ReportLine.create(
            coverage=coverage,
            type=coverage_type_str,
            sessions=[
                LineSession(
                    id=sessionid,
                    coverage=coverage,
                    branches=missing_branches,
                    partials=partials,
                    complexity=complexity,
                )
            ],
            complexity=complexity,
        )


class ReportBuilder:
    def __init__(
        self,
        current_yaml: UserYaml,
        sessionid: int,
        ignored_lines: dict,
        path_fixer: PathFixer,
    ):
        self.current_yaml = current_yaml
        self.sessionid = sessionid
        self.ignored_lines = ignored_lines
        self.path_fixer = path_fixer

    def create_report_builder_session(self, filepath) -> ReportBuilderSession:
        return ReportBuilderSession(self, filepath)
