from ariadne import InterfaceType, ObjectType, UnionType

from graphql_api.helpers.connection import (
    ArrayConnection,
    Connection,
)
from graphql_api.types.errors import MissingCoverage, MissingHeadReport, UnknownPath
from graphql_api.types.errors.errors import UnknownFlags
from services.path import Dir, File

path_content_bindable = InterfaceType("PathContent")
path_content_file_bindable = ObjectType("PathContentFile")


@path_content_bindable.type_resolver
def resolve_path_content_type(obj, *_):
    if isinstance(obj, File):
        return "PathContentFile"
    if isinstance(obj, Dir):
        return "PathContentDir"
    return None


@path_content_bindable.field("name")
def resolve_name(item: File | Dir, info) -> str:
    return item.name


@path_content_bindable.field("path")
def resolve_file_path(item: File | Dir, info) -> str:
    return item.full_path


@path_content_bindable.field("hits")
def resolve_hits(item: File | Dir, info) -> int:
    return item.hits


@path_content_bindable.field("misses")
def resolve_misses(item: File | Dir, info) -> int:
    return item.misses


@path_content_bindable.field("partials")
def resolve_partials(item: File | Dir, info) -> int:
    return item.partials


@path_content_bindable.field("lines")
def resolve_lines(item: File | Dir, info) -> int:
    return item.lines


@path_content_bindable.field("percentCovered")
def resolve_percent_covered(item: File | Dir, info) -> float:
    return item.coverage


path_contents_result_bindable = UnionType("PathContentsResult")


@path_contents_result_bindable.type_resolver
def resolve_path_contents_result_type(res, *_):
    if isinstance(res, MissingHeadReport):
        return "MissingHeadReport"
    elif isinstance(res, MissingCoverage):
        return "MissingCoverage"
    elif isinstance(res, UnknownPath):
        return "UnknownPath"
    elif isinstance(res, UnknownFlags):
        return "UnknownFlags"
    if isinstance(res, type({"results": list[File | Dir]})):
        return "PathContents"


deprecated_path_contents_result_bindable = UnionType("DeprecatedPathContentsResult")


@deprecated_path_contents_result_bindable.type_resolver
def resolve_deprecated_path_contents_result_type(res, *_):
    if isinstance(res, MissingHeadReport):
        return "MissingHeadReport"
    elif isinstance(res, MissingCoverage):
        return "MissingCoverage"
    elif isinstance(res, UnknownPath):
        return "UnknownPath"
    elif isinstance(res, UnknownFlags):
        return "UnknownFlags"
    elif isinstance(res, Connection | ArrayConnection):
        return "PathContentConnection"
