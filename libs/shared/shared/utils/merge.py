from collections import defaultdict
from enum import IntEnum
from fractions import Fraction
from itertools import groupby

from shared.reports.types import LineSession, ReportLine


def merge_all(coverages, missing_branches=None):
    if len(coverages) == 1:
        return coverages[0]

    cov = coverages[0]
    for _ in coverages[1:]:
        cov = merge_coverage(cov, _, missing_branches)
    return cov


def merge_branch(b1, b2):
    if b1 == b2:  # 1/2 == 1/2
        return b1
    if b1 == -1 or b2 == -1:
        return -1
    if isinstance(b1, int) and not isinstance(b1, bool) and b1 > 0:
        return b1
    if isinstance(b2, int) and not isinstance(b2, bool) and b2 > 0:
        return b2
    if b1 in (0, None, True):
        return b2
    if b2 in (0, None, True):
        return b1
    if isinstance(b1, list):
        return b1
    if isinstance(b2, list):
        return b2
    br1, br2 = b1.split("/", 1)
    if br1 == br2:  # equal 1/1
        return b1
    br3, br4 = b2.split("/", 1)
    if br3 == br4:  # equal 1/1
        return b2
    # return the greatest found
    return (
        f"{br1 if int(br1) > int(br3) else br3}/{br2 if int(br2) > int(br4) else br4}"
    )


def merge_partial_line(p1, p2):
    if not p1 or not p2:
        return p1 or p2

    np = p1 + p2
    if len(np) == 1:
        # one result already
        return np

    fl = defaultdict(list)
    [
        [fl[x].append(_c) for x in range(_s or 0, _e + 1)]
        for _s, _e, _c in np
        if _e is not None
    ]
    ks = list(fl.keys())
    mx = max(ks) + 1 if ks else 0
    # appends coverage on each column when [X, None, C]
    [[fl[x].append(_c) for x in range(_s or 0, mx)] for _s, _e, _c in np if _e is None]
    ks = list(fl.keys())
    # fl = {1: [1], 2: [1], 4: [0], 3: [1], 5: [0], 7: [0], 8: [0]}
    pp = []
    append = pp.append
    for cov, group in groupby(
        sorted([(cl, max(cv)) for cl, cv in list(fl.items())]), lambda c: c[1]
    ):
        group = list(group)  # noqa: PLW2901
        append(_ifg(group[0][0], group[-1][0], cov))

    # never ends
    if [[max(ks), None, _c] for _s, _e, _c in np if _e is None]:
        pp[-1][1] = None

    return pp


def merge_coverage(l1, l2, branches_missing=True):
    if l1 is None or l2 is None:
        return l1 if l1 is not None else l2

    elif l1 == -1 or l2 == -1:
        # ignored line
        return -1

    l1t = cast_ints_float(l1)
    l2t = cast_ints_float(l2)

    if isinstance(l1t, float | Fraction) and isinstance(l2t, float | Fraction):
        return l1 if l1 >= l2 else l2

    elif isinstance(l1t, str) or isinstance(l2t, str):
        if isinstance(l1t, float):
            # using or here because if l1 is 0 return l2
            # this will trigger 100% if l1 is > 0
            branches_missing = [] if l1 else False
            l1 = l2

        elif isinstance(l2t, float):
            branches_missing = [] if l2 else False

        if branches_missing == []:
            # all branches were hit, no need to merge them
            l1 = l1.split("/")[-1]
            return f"{l1}/{l1}"

        elif isinstance(branches_missing, list):
            # we know how many are missing
            target = int(l1.split("/")[-1])
            bf = target - len(branches_missing)
            return f"{bf if bf > 0 else 0}/{target}"

        return merge_branch(l1, l2)

    elif isinstance(l1t, list) and isinstance(l2t, list):
        return merge_partial_line(l1, l2)

    elif isinstance(l1t, bool) or isinstance(l2t, bool):
        return (l2 or l1) if isinstance(l1t, bool) else (l1 or l2)

    return merge_coverage(
        partials_to_line(l1) if isinstance(l1t, list) else l1,
        partials_to_line(l2) if isinstance(l2t, list) else l2,
    )


def merge_missed_branches(sessions: list[LineSession]) -> list | None:
    """
    Returns a list of missed branches, defined as the *intersection* of all
    the missed branches of the input sessions.

    Returns `None` if there is no sessions or no missed branches in the sessions.
    Returns an empty list (no missed branches) if the line was fully covered,
      or the missed branches are disjoint.
    """
    if not sessions or not any(s.branches is not None for s in sessions):
        return None

    missed_branches: None | set = None
    for session in sessions:
        if session.branches is None:
            if line_type(session.coverage) == LineType.hit:
                return []
            continue
        if missed_branches is None:
            missed_branches = set(session.branches)
        else:
            missed_branches.intersection_update(session.branches)
            if not missed_branches:
                return []

    return list(missed_branches) if missed_branches is not None else None


def merge_line(l1, l2, joined=True, is_disjoint=False):
    if not l1 or not l2:
        return l1 or l2

    if joined and is_disjoint:
        sessions = list(l1.sessions or [])
        sessions.extend(l2.sessions or [])
        return ReportLine.create(type=l1.type or l2.type, sessions=sessions)

    # merge sessions
    sessions = _merge_sessions(list(l1.sessions or []), list(l2.sessions or []))

    return ReportLine.create(
        type=l1.type or l2.type,
        coverage=get_coverage_from_sessions(sessions) if joined else l1.coverage,
        complexity=get_complexity_from_sessions(sessions) if joined else l1.complexity,
        sessions=sessions,
    )


def merge_line_session(s1, s2):
    s1b = s1.branches
    s2b = s2.branches
    if s1b is None and s2b is None:
        # all are None, so return None
        mb = None
    elif s1b is None:
        if line_type(s1.coverage) == 0:
            # s1 was a hit, so we have no more branches to get
            mb = []
        else:
            mb = s2b
    elif s2b is None:
        if line_type(s2.coverage) == 0:
            # s2 was a hit, so we have no more branches to get
            mb = []
        else:
            mb = s1b
    else:
        mb = list(set(s1b or []) & set(s2b or []))

    s1p = s1.partials
    s2p = s2.partials
    partials = None
    if s1p or s2p:
        if s1p is None or s2p is None:
            partials = s1p or s2p
        else:
            # list + list
            partials = sorted(s1p + s2p, key=lambda p: p[0])

    return LineSession(
        s1.id, merge_coverage(s1.coverage, s2.coverage, mb), mb, partials
    )


def _merge_sessions(s1: list[LineSession], s2: list[LineSession]) -> list[LineSession]:
    """Merges two lists of different sessions into one"""
    if not s1 or not s2:
        return s1 or s2

    session_ids_1 = {s.id for s in s1}
    session_ids_2 = {s.id for s in s2}
    intersection = session_ids_1.intersection(session_ids_2)
    if not intersection:
        s1.extend(s2)
        return s1

    sessions_1 = {s.id: s for s in s1}
    sessions_2 = {s.id: s for s in s2}

    # merge existing
    for session_id in intersection:
        sessions_1[session_id] = merge_line_session(
            sessions_1[session_id], sessions_2.pop(session_id)
        )

    # add remaining new sessions
    return list(sessions_1.values()) + list(sessions_2.values())


def _ifg(s, e, c):
    """
    s=start, e=end, c=coverage
    Insures the end is larger then the start.
    """
    return [s, e if e > s else s + 1, c]


def cast_ints_float(value):
    """
    When doing a merge we'd like to convert all ints to floats. this method takes in a value and
    converts it to flaot if type(value) is int
    """
    return value if not isinstance(value, int) else float(value)


class LineType(IntEnum):
    skipped = -1
    hit = 0
    miss = 1
    partial = 2


def line_type(line) -> LineType | None:
    """
    -1 = skipped (had coverage data, but fixed out)
    0 = hit
    1 = miss
    2 = partial
    None = ignore (because it has messages or something)
    """
    if line is True:
        return LineType.partial
    if isinstance(line, str):
        return branch_type(line)
    if line == -1:
        return LineType.skipped
    if line is False:
        return None
    if isinstance(line, Fraction):
        if line == 0:
            return LineType.miss
        if line >= 1:
            return LineType.hit
        return LineType.partial
    if line:
        return LineType.hit
    if line is not None:
        return LineType.miss
    return None


def branch_type(b):
    """
    0 = hit
    1 = miss
    2 = partial
    """
    if "/" not in b:
        if int(b) == 0:
            return LineType.miss
        return LineType.hit
    b1, b2 = tuple(b.split("/", 1))
    return (
        LineType.hit if b1 == b2 else LineType.miss if b1 == "0" else LineType.partial
    )


def partials_to_line(partials):
    """
        | . . . . . |
    in:   1 1 1 0 0
    out: 1/2
        | . . . . . |
    in:   1 0 1 0 0
    out: 2/4
    """
    ln = len(partials)
    if ln == 1:
        return partials[0][2]
    v = sum(1 for (sc, ec, hits) in partials if hits > 0)
    return f"{v}/{ln}"


def get_complexity_from_sessions(sessions):
    _type = type(sessions[0].complexity)
    if _type is int:
        return max((s.complexity or 0) for s in sessions)
    elif _type in (tuple, list):
        return (
            max((s.complexity or (0, 0))[0] for s in sessions),
            max((s.complexity or (0, 0))[1] for s in sessions),
        )


def get_coverage_from_sessions(sessions):
    new_coverages = [s.coverage for s in sessions]
    return merge_all(new_coverages, merge_missed_branches(sessions))
