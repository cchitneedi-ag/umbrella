import dataclasses
import logging
from copy import copy
from typing import Any

import sentry_sdk

from shared.helpers.flag import Flag
from shared.helpers.yaml import walk
from shared.reports.diff import CalculatedDiff, RawDiff, calculate_report_diff
from shared.reports.filtered import FilteredReport
from shared.reports.reportfile import ReportFile
from shared.reports.types import ReportLine, ReportTotals
from shared.utils.flare import report_to_flare
from shared.utils.make_network_file import make_network_file
from shared.utils.merge import get_complexity_from_sessions, get_coverage_from_sessions
from shared.utils.migrate import migrate_totals
from shared.utils.sessions import Session, SessionType
from shared.utils.totals import agg_totals

from .serde import END_OF_CHUNK, END_OF_HEADER, serialize_report

log = logging.getLogger(__name__)


class Report:
    sessions: dict[int, Session]
    _totals: ReportTotals | None
    _files: dict[str, ReportFile]

    def __init__(
        self,
        files: dict[str, tuple[int, ReportTotals, Any, ReportTotals]] | None = None,
        sessions: dict[int | str, Session | dict] | None = None,
        totals=None,
        chunks=None,
        diff_totals=None,
        **kwargs,
    ):
        self.sessions = {}
        self._totals = None
        self._files = {}

        if sessions:
            self.sessions = {
                int(sid): copy(session)
                if isinstance(session, Session)
                else Session.parse_session(session.pop("id", int(sid)), **session)
                for sid, session in sessions.items()
            }

        _chunks: list[str] = []
        if chunks:
            if isinstance(chunks, bytes):
                chunks = chunks.decode()
            if isinstance(chunks, str):
                splits = chunks.split(END_OF_HEADER, maxsplit=1)
                if len(splits) > 1:
                    chunks = splits[1]

                _chunks = chunks.split(END_OF_CHUNK)
            else:
                _chunks = chunks

        if files:
            for name, summary in files.items():
                chunks_index = summary[0]
                file_totals = summary[1]
                try:
                    # Indices 2 and 3 may not exist. Index 2 used to be `session_totals`
                    # but is ignored now due to a bug.
                    file_diff_totals = summary[3]
                except IndexError:
                    file_diff_totals = None

                try:
                    lines = _chunks[chunks_index]
                except IndexError:
                    lines = ""

                self._files[name] = ReportFile(
                    name, totals=file_totals, lines=lines, diff_totals=file_diff_totals
                )

        if isinstance(totals, ReportTotals):
            self._totals = totals
        elif totals:
            self._totals = ReportTotals(*migrate_totals(totals))

        self.diff_totals = diff_totals

    def _invalidate_caches(self):
        self._totals = None

    @property
    def totals(self):
        if not self._totals:
            self._totals = self._process_totals()
        return self._totals

    def _process_totals(self):
        """Runs through the file network to aggregate totals
        returns <ReportTotals>
        """

        totals = agg_totals(file.totals for file in self._files.values())
        totals.sessions = len(self.sessions)
        return totals

    @classmethod
    def from_chunks(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def has_precalculated_totals(self):
        return self._totals is not None

    @property
    def network(self):
        for fname, data in self._files.items():
            yield (
                fname,
                make_network_file(data.totals, data.diff_totals),
            )

    def __repr__(self):
        try:
            return "<{} files={}>".format(
                self.__class__.__name__,
                len(getattr(self, "_files", [])),
            )
        except Exception:
            return f"<{self.__class__.__name__} files=n/a>"

    @property
    def files(self) -> list[str]:
        """returns a list of files in the report"""
        return list(self._files.keys())

    @property
    def flags(self):
        """returns dict(:name=<Flag>)"""
        flags_dict = {}
        for session in self.sessions.values():
            if session.flags:
                # If the session was carriedforward, mark its flags as carriedforward
                session_carriedforward = (
                    session.session_type == SessionType.carriedforward
                )
                session_carriedforward_from = getattr(
                    session, "session_extras", {}
                ).get("carriedforward_from")

                for flag in session.flags:
                    flags_dict[flag] = Flag(
                        self,
                        flag,
                        carriedforward=session_carriedforward,
                        carriedforward_from=session_carriedforward_from,
                    )
        return flags_dict

    def get_flag_names(self) -> list[str]:
        all_flags = set()
        for session in self.sessions.values():
            if session and session.flags:
                all_flags.update(session.flags)
        return sorted(all_flags)

    def append(self, _file, joined=True, is_disjoint=False):
        """adds or merged a file into the report"""
        if _file is None:
            # skip empty adds
            return False

        elif not isinstance(_file, ReportFile):
            raise TypeError(f"expecting ReportFile got {type(_file)}")

        elif len(_file) == 0:
            # dont append empty files
            return False

        assert _file.name, "file must have a name"

        existing_file = self._files.get(_file.name)
        if existing_file is not None:
            existing_file.merge(_file, joined, is_disjoint)
        else:
            self._files[_file.name] = _file

        self._invalidate_caches()
        return True

    def get(self, filename):
        return self._files.get(filename)

    def resolve_paths(self, paths: list[tuple[str, str | None]]):
        for old, new in paths:
            if old in self._files:
                self.rename(old, new)

    def rename(self, old: str, new: str | None):
        file = self._files.pop(old)
        if file is not None:
            if new:
                file.name = new
                self._files[new] = file

        self._invalidate_caches()
        return True

    def __getitem__(self, filename):
        _file = self.get(filename)
        if _file is None:
            raise IndexError(f"File at path {filename} not found in report")
        return _file

    def __delitem__(self, filename):
        self._files.pop(filename)
        return True

    def get_file_totals(self, path: str) -> ReportTotals | None:
        file = self._files.get(path)
        if file is None:
            log.warning(
                "Fetching file totals for a file that isn't in the report",
                extra={"path": path},
            )
            return None

        return file.totals

    def next_session_number(self):
        start_number = len(self.sessions)
        while start_number in self.sessions or str(start_number) in self.sessions:
            start_number += 1
        return start_number

    def add_session(self, session, use_id_from_session=False):
        sessionid = session.id if use_id_from_session else self.next_session_number()
        self.sessions[sessionid] = session
        if self._totals:
            # add session to totals
            if use_id_from_session:
                self._totals = dataclasses.replace(
                    self._totals, sessions=self._totals.sessions + 1
                )
            else:
                self._totals = dataclasses.replace(self._totals, sessions=sessionid + 1)

        return sessionid, session

    def __iter__(self):
        """Iter through all the files
        yielding <ReportFile>
        """
        yield from self._files.values()

    def __contains__(self, filename):
        return filename in self._files

    @sentry_sdk.trace
    def merge(self, new_report, joined=True, is_disjoint=False):
        """
        Merge the `new_report` into this one.

        If `joined=False`, that means that any coverage information from `new_report` takes precedence.
        Otherwise, the existing and new coverage `ReportLine` records are being merged.

        If `is_disjoint=True` is specified, all coverage records from `new_report` will be *appended* to this report.
        A later call to `finish_merge` will then fully merge those coverage record.
        This in an optimization when the `merge` fn is being called multiple times with multiple `Report`s,
        as intermediate merge steps can be avoided in favor of only doing one merge step at the end.
        """
        """combine report data from another"""
        if new_report is None:
            return

        elif not isinstance(new_report, Report):
            raise TypeError(f"expecting type Report got {type(new_report)}")

        elif new_report.is_empty():
            return

        # merge files
        for _file in new_report:
            if _file.name:
                self.append(_file, joined, is_disjoint)

    @sentry_sdk.trace
    def finish_merge(self):
        """
        When calling `merge(is_disjoint=True)` above, the line records are not fully merged.
        This function here is iterating over all those lines once more, to make sure they are.

        This is an optimization to avoid having to repeatedly merge line records.
        Instead, the `merge` code above just appends disjoint session records,
        and this `finish_merge` is then fully merging those in one go.
        """

        for file in self:
            if not file._parsed_lines:
                continue
            for line in file._parsed_lines:
                if isinstance(line, ReportLine) and line.coverage is None:
                    line.coverage = get_coverage_from_sessions(line.sessions)
                    line.complexity = get_complexity_from_sessions(line.sessions)

    def is_empty(self):
        """returns boolean if the report has no content"""
        return len(self._files) == 0

    def __bool__(self):
        return self.is_empty() is False

    def serialize(self, with_totals=True) -> tuple[bytes, bytes, ReportTotals | None]:
        """
        Serializes a report as `(report_json, chunks, totals)`.

        The `totals` is either a `ReportTotals`, or `None`, depending on the `with_totals` flag.
        """
        return serialize_report(self, with_totals)

    @sentry_sdk.trace
    def flare(self, changes=None, color=None):
        if changes is not None:
            """
            if changes are provided we produce a new network
            only pass totals if they change
            """
            # <dict path: totals if not new else None>
            changed_coverages = {
                individual_change.path: individual_change.totals.coverage
                if not individual_change.new and individual_change.totals
                else None
                for individual_change in changes
            }
            # <dict path: stripeed if not in_diff>
            classes = {_Change.path: "s" for _Change in changes if not _Change.in_diff}

            def _network():
                for name, _NetworkFile in self.network:
                    changed_coverage = changed_coverages.get(name)
                    if changed_coverage:
                        # changed file
                        yield (
                            name,
                            ReportTotals(
                                lines=_NetworkFile.totals.lines,
                                coverage=float(changed_coverage),
                            ),
                        )
                    else:
                        diff = _NetworkFile.diff_totals
                        if diff and diff.lines > 0:  # lines > 0
                            # diff file
                            yield (
                                name,
                                ReportTotals(
                                    lines=_NetworkFile.totals.lines,
                                    coverage=-1
                                    if float(diff.coverage)
                                    < float(_NetworkFile.totals.coverage)
                                    else 1,
                                ),
                            )

                        else:
                            # unchanged file
                            yield name, ReportTotals(lines=_NetworkFile.totals.lines)

            network = _network()

            def color(cov):
                return (
                    "purple"
                    if cov is None
                    else "#e1e1e1"
                    if cov == 0
                    else "green"
                    if cov > 0
                    else "red"
                )

        else:
            network = (
                (path, _NetworkFile.totals) for path, _NetworkFile in self.network
            )
            classes = {}
            # [TODO] [v4.4.0] remove yaml from args, use below
            # color = self.yaml.get(('coverage', 'range'))

        return report_to_flare(network, color, classes)

    def filter(self, paths=None, flags=None):
        if paths:
            if not isinstance(paths, list | set | tuple):
                raise TypeError(f"expecting list for argument paths got {type(paths)}")
        if paths is None and flags is None:
            return self
        return FilteredReport(self, path_patterns=paths, flags=flags)

    @sentry_sdk.trace
    def does_diff_adjust_tracked_lines(self, diff, future_report, future_diff):
        """
        Returns <boolean> if the diff touches tracked lines

        master . A . C
        pull          | . . B

        :diff = <diff> A...C
        :future_report = <report> B
        :future_diff = <diff> C...B

        future_report is necessary because it is used to determin if
        lines added in the diff are tracked by codecov
        """
        if diff and diff.get("files"):
            for path, data in diff["files"].items():
                future_state = walk(future_diff, ("files", path, "type"))
                if data["type"] == "deleted" and path in self:  # deleted  # and tracked
                    # found a file that was tracked and deleted
                    return True

                elif (
                    data["type"] == "new"
                    and future_state != "deleted"  # newly tracked
                    and path  # not deleted in future
                    in future_report  # found in future
                ):
                    # newly tracked file
                    return True

                elif data["type"] == "modified":
                    in_past = path in self
                    in_future = future_state != "deleted" and path in future_report
                    if in_past and in_future:
                        # get the future version
                        future_file = future_report.get(path)
                        # if modified
                        if future_state == "modified":
                            # shift the lines to "guess" what C was
                            future_file.shift_lines_by_diff(
                                future_diff["files"][path], forward=False
                            )

                        if self.get(path).does_diff_adjust_tracked_lines(
                            data, future_file
                        ):
                            # lines changed
                            return True

                    elif in_past and not in_future:
                        # missing in future
                        return True

                    elif not in_past and in_future:
                        # missing in pats
                        return True

        return False

    @sentry_sdk.trace
    def shift_lines_by_diff(self, diff, forward=True):
        """
        [volitile] will permanently adjust repot report

        Takes a <diff> and offsets the line based on additions and removals
        """
        if diff and diff.get("files"):
            for path, data in diff["files"].items():
                if data["type"] == "modified" and path in self:
                    file = self.get(path)
                    file.shift_lines_by_diff(data, forward=forward)

    def calculate_diff(self, diff: RawDiff) -> CalculatedDiff:
        """
        Calculates the per-file totals (and total) of the parts
            from a `git diff` that are relevant in the report
        """
        return calculate_report_diff(self, diff)

    def save_diff_calculation(self, diff, diff_result):
        diff["totals"] = diff_result["general"]
        self.diff_totals = diff["totals"]
        for filename, file_totals in diff_result["files"].items():
            data = diff["files"].get(filename)
            data["totals"] = file_totals
            file = self._files[filename]
            if file_totals.lines == 0:
                file_totals = dataclasses.replace(  # noqa: PLW2901
                    file_totals, coverage=None, complexity=None, complexity_total=None
                )
            file.diff_totals = file_totals

    @sentry_sdk.trace
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

    def get_uploaded_flags(self):
        flags = set()
        for sess in self.sessions.values():
            if sess.session_type == SessionType.uploaded and sess.flags is not None:
                flags.update(sess.flags)
        return flags

    def delete_multiple_sessions(self, session_ids_to_delete: set[int]):
        for sessionid in session_ids_to_delete:
            self.sessions.pop(sessionid)

        files_to_delete = []
        for file in self:
            file.delete_multiple_sessions(session_ids_to_delete)
            if not file:
                files_to_delete.append(file.name)
        for file in files_to_delete:
            del self[file]

        self._invalidate_caches()

    @sentry_sdk.trace
    def change_sessionid(self, old_id: int, new_id: int):
        """
        This changes the session with `old_id` to have `new_id` instead.
        It patches up all the references to that session across all files and line records.

        In particular, it changes the id in all the `LineSession`s,
        and does the equivalent of `calculate_present_sessions`.
        """
        session = self.sessions[new_id] = self.sessions.pop(old_id)
        session.id = new_id

        for file in self:
            all_sessions = set()

            for idx, _line in enumerate(file._lines):
                if not _line:
                    continue

                # this turns the line into an actual `ReportLine`
                line = file._lines[idx] = file._line(_line)

                for session in line.sessions:
                    if session.id == old_id:
                        session.id = new_id
                    all_sessions.add(session.id)

            file._invalidate_caches()
            file.__present_sessions = all_sessions

        self._invalidate_caches()
