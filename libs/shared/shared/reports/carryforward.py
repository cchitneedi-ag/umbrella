import logging
import re
from collections.abc import Mapping, Sequence

from shared.reports.resources import Report
from shared.utils.match import Matcher
from shared.utils.sessions import SessionType

log = logging.getLogger(__name__)


def carriedforward_session_name(original_session_name: str) -> str:
    if not original_session_name:
        return "Carriedforward"
    elif original_session_name.startswith("CF "):
        count = 0
        current_name = original_session_name
        while current_name.startswith("CF "):
            current_name = current_name.replace("CF ", "", 1)
            count += 1
        return f"CF[{count + 1}] - {current_name}"
    elif original_session_name.startswith("CF"):
        regex = r"CF\[(\d*)\]"
        res = re.match(regex, original_session_name)
        if res:
            number_so_far = int(res.group(1))
            return re.sub(
                regex, f"CF[{number_so_far + 1}]", original_session_name, count=1
            )
    return f"CF[1] - {original_session_name}"


def generate_carryforward_report(
    report: Report,
    flags: Sequence[str],
    paths: Sequence[str],
    session_extras: Mapping[str, str] | None = None,
) -> Report:
    """
    Generates a carriedforward report by filtering the given `report` in-place,
    to only those files and sessions matching the given `flags` and `paths`.

    The sessions that are matching the `flags` are being flagged as `carriedforward`,
    and other sessions are removed from the report."""
    if paths:
        matcher = Matcher(paths)
        files_to_delete = {
            filename for filename in report._files.keys() if not matcher.match(filename)
        }
        for filename in files_to_delete:
            del report[filename]

    sessions_to_delete = set()
    for sid, session in report.sessions.items():
        if not contain_any_of_the_flags(flags, session.flags):
            sessions_to_delete.add(int(sid))
        else:
            session.session_extras = session_extras or session.session_extras
            session.name = carriedforward_session_name(session.name)
            session.session_type = SessionType.carriedforward
    log.info(
        "Removing sessions that are not supposed to carryforward",
        extra={"deleted_sessions": sessions_to_delete},
    )
    report.delete_multiple_sessions(sessions_to_delete)
    return report


def contain_any_of_the_flags(expected_flags, actual_flags):
    if expected_flags is None or actual_flags is None:
        return False
    return len(set(expected_flags) & set(actual_flags)) > 0
