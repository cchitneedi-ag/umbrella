from ariadne import EnumType

from .enums import (
    ComparisonError,
    CoverageLine,
    GoalOnboarding,
    OrderingDirection,
    PathContentsValue,
    PullRequestState,
    RepositoryOrdering,
    TypeProjectOnboarding,
    UploadErrorEnum,
    UploadState,
    UploadType,
)

enum_types = [
    EnumType("RepositoryOrdering", RepositoryOrdering),
    EnumType("OrderingDirection", OrderingDirection),
    EnumType("CoverageLine", CoverageLine),
    EnumType("ComparisonError", ComparisonError),
    EnumType("TypeProjectOnboarding", TypeProjectOnboarding),
    EnumType("GoalOnboarding", GoalOnboarding),
    EnumType("PathContentsValue", PathContentsValue),
    EnumType("PullRequestState", PullRequestState),
    EnumType("UploadState", UploadState),
    EnumType("UploadType", UploadType),
    EnumType("UploadErrorEnum", UploadErrorEnum),
]
