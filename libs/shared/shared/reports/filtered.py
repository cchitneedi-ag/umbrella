import dataclasses
import logging

from shared.reports.diff import (
    CalculatedDiff,
    DiffSegment,
    RawDiff,
    calculate_file_diff,
    calculate_report_diff,
)
from shared.reports.totals import get_line_totals
from shared.reports.types import EMPTY, ReportTotals
from shared.utils.make_network_file import make_network_file
from shared.utils.match import Matcher
from shared.utils.merge import get_complexity_from_sessions, merge_all
from shared.utils.totals import agg_totals

log = logging.getLogger(__name__)


def _contain_any_of_the_flags(expected_flags, actual_flags):
    if expected_flags is None or actual_flags is None:
        return False
    return len(set(expected_flags) & set(actual_flags)) > 0


class FilteredReportFile:
    __slots__ = ["report_file", "session_ids", "_totals", "_cached_lines"]

    def __init__(self, report_file, session_ids):
        self.report_file = report_file
        self.session_ids = session_ids
        self._totals = None
        self._cached_lines = None

    def line_modifier(self, line):
        new_sessions = [s for s in line.sessions if s.id in self.session_ids]
        if len(new_sessions) == 0:
            return EMPTY
        remaining_coverages = [s.coverage for s in new_sessions]
        new_coverage = merge_all(remaining_coverages)
        return dataclasses.replace(
            line,
            complexity=get_complexity_from_sessions(new_sessions),
            sessions=new_sessions,
            coverage=new_coverage,
        )

    @property
    def name(self):
        return self.report_file.name

    @property
    def totals(self):
        if not self._totals:
            self._totals = self._process_totals()
        return self._totals

    @property
    def eof(self):
        return self.report_file.eof

    @property
    def lines(self):
        """Iter through lines with coverage
        returning (ln, line)
        <generator ((3, Line), (4, Line), (7, Line), ...)>
        """
        if self._cached_lines:
            return self._cached_lines
        ret = []
        for ln, line in self.report_file.lines:
            line = self.line_modifier(line)  # noqa: PLW2901
            if line:
                ret.append((ln, line))
        self._cached_lines = ret
        return ret

    def calculate_diff(self, segments: list[DiffSegment]) -> ReportTotals:
        return calculate_file_diff(self, segments)

    def get(self, ln):
        line = self.report_file.get(ln)
        if line:
            line = self.line_modifier(line)
            if not line:
                return None
            return line

    def _process_totals(self):
        """return dict of totals"""
        return get_line_totals(line for _ln, line in self.lines)


class FilteredReport:
    def __init__(self, report, path_patterns, flags):
        self.report = report
        self.path_patterns = path_patterns
        self._matcher = Matcher(path_patterns)
        self.flags = flags
        self._totals = None
        self._sessions_to_include = None
        self.report_file_cache = {}

    def has_precalculated_totals(self):
        return self._totals is not None

    def _calculate_sessionids_to_include(self):
        if not self.flags:
            return set(self.report.sessions.keys())
        return {
            sid
            for (sid, session) in self.report.sessions.items()
            if _contain_any_of_the_flags(self.flags, session.flags)
        }

    @property
    def session_ids_to_include(self):
        if self._sessions_to_include is None:
            self._sessions_to_include = self._calculate_sessionids_to_include()
        return self._sessions_to_include

    def should_include(self, filename):
        return self._matcher.match(filename)

    @property
    def network(self):
        for fname in self.report._files.keys():
            file = self.get(fname)
            if file:
                yield fname, make_network_file(file.totals)

    def get(self, filename):
        if not self.should_include(filename):
            return None
        if not self.flags:
            return self.report.get(filename)
        r = self.report.get(filename)
        if r is None:
            return None

        if filename not in self.report_file_cache:
            self.report_file_cache[filename] = FilteredReportFile(
                r, self.session_ids_to_include
            )
        return self.report_file_cache[filename]

    @property
    def files(self):
        return [f for f in self.report.files if self.should_include(f)]

    def get_file_totals(self, path):
        if self.should_include(path):
            return self.report.get_file_totals(path)

        return None

    @property
    def totals(self):
        if not self._totals:
            self._totals = self._process_totals()
        return self._totals

    def is_empty(self):
        return not any(self.should_include(x) for x in self.report._files.keys())

    def _iter_totals(self):
        for filename in self.report._files.keys():
            if self.should_include(filename):
                res = self.get(filename).totals
                if res and res.lines > 0:
                    yield res

    def _process_totals(self):
        """Runs through the file network to aggregate totals
        returns <ReportTotals>
        """
        totals = agg_totals(self._iter_totals())
        totals.sessions = len(self.session_ids_to_include)
        return ReportTotals(*tuple(totals))

    def calculate_diff(self, diff: RawDiff) -> CalculatedDiff:
        """
        Calculates the per-file totals (and total) of the parts
            from a `git diff` that are relevant in the report
        """
        return calculate_report_diff(self, diff)

    def apply_diff(self, diff, _save=True):
        """
        Add coverage details to the diff at ['coverage'] = <ReportTotals>
        returns <ReportTotals>
        """
        if not diff or not diff.get("files"):
            return None
        totals = self.calculate_diff(diff)
        if _save and totals:
            self.save_diff_calculation(diff, totals)
        return totals.get("general")

    def save_diff_calculation(self, diff, diff_result):
        diff["totals"] = diff_result["general"]
        self.diff_totals = diff["totals"]
        for filename, file_totals in diff_result["files"].items():
            data = diff["files"].get(filename)
            data["totals"] = file_totals

    def __iter__(self):
        """Iter through all the files
        yielding <ReportFile>
        """
        for file in self.report:
            if self.should_include(file.name):
                if not self.flags:
                    yield file
                else:
                    yield FilteredReportFile(file, self.session_ids_to_include)
