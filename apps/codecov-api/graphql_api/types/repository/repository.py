import logging
from datetime import datetime
from typing import Any

import sentry_sdk
import yaml
from ariadne import ObjectType, UnionType
from asgiref.sync import sync_to_async
from django.conf import settings
from graphql.type.definition import GraphQLResolveInfo

import shared.rate_limits as rate_limits
from codecov_auth.models import SERVICE_GITHUB, SERVICE_GITHUB_ENTERPRISE, Owner
from core.models import Branch, Commit, Pull, Repository
from graphql_api.actions.commits import load_commit_statuses, repo_commits
from graphql_api.dataloader.commit import CommitLoader
from graphql_api.dataloader.owner import OwnerLoader
from graphql_api.helpers.connection import queryset_to_connection
from graphql_api.helpers.requested_fields import selected_fields
from graphql_api.types.coverage_analytics.coverage_analytics import (
    CoverageAnalyticsProps,
)
from graphql_api.types.enums import OrderingDirection
from graphql_api.types.enums.enum_types import PullRequestState
from graphql_api.types.errors.errors import NotFoundError, OwnerNotActivatedError
from shared.helpers.redis import get_redis_connection

TOKEN_UNAVAILABLE = "Token Unavailable. Please contact your admin."

log = logging.getLogger(__name__)

repository_bindable = ObjectType("Repository")

repository_bindable.set_alias("updatedAt", "updatestamp")

# latest_commit_at and coverage have their NULL value defaulted to -1/an old date
# so the NULL would end up last in the queryset as we do not have control over
# the order_by call. The true value of is under true_*; which would actually contain NULL
# see with_cache_latest_commit_at() from core/managers.py
repository_bindable.set_alias("latestCommitAt", "true_latest_commit_at")


@repository_bindable.field("repoid")
def resolve_repoid(repository: Repository, info: GraphQLResolveInfo) -> int:
    return repository.repoid


@repository_bindable.field("name")
def resolve_name(repository: Repository, info: GraphQLResolveInfo) -> str:
    return repository.name


@repository_bindable.field("oldestCommitAt")
def resolve_oldest_commit_at(
    repository: Repository, info: GraphQLResolveInfo
) -> datetime | None:
    if hasattr(repository, "oldest_commit_at"):
        return repository.oldest_commit_at
    else:
        return None


@repository_bindable.field("branch")
def resolve_branch(
    repository: Repository, info: GraphQLResolveInfo, name: str
) -> Branch:
    command = info.context["executor"].get_command("branch")
    return command.fetch_branch(repository, name)


@repository_bindable.field("author")
def resolve_author(repository: Repository, info: GraphQLResolveInfo) -> Owner:
    return OwnerLoader.loader(info).load(repository.author_id)


@repository_bindable.field("commit")
def resolve_commit(repository: Repository, info: GraphQLResolveInfo, id: str) -> Commit:
    loader = CommitLoader.loader(info, repository.pk)
    commit = loader.load(id)

    if commit:
        sentry_sdk.set_tag("commit_sha", id)

    return commit


@repository_bindable.field("uploadToken")
def resolve_upload_token(repository: Repository, info: GraphQLResolveInfo) -> str:
    should_hide_tokens = settings.HIDE_ALL_CODECOV_TOKENS

    current_owner = info.context["request"].current_owner
    if not current_owner:
        is_current_user_admin = False
    else:
        is_current_user_admin = current_owner.is_admin(repository.author)

    if should_hide_tokens and not is_current_user_admin:
        return TOKEN_UNAVAILABLE
    command = info.context["executor"].get_command("repository")
    return command.get_upload_token(repository)


@repository_bindable.field("pull")
def resolve_pull(repository: Repository, info: GraphQLResolveInfo, id: int) -> Pull:
    command = info.context["executor"].get_command("pull")
    return command.fetch_pull_request(repository, id)


@repository_bindable.field("pulls")
async def resolve_pulls(
    repository: Repository,
    info: GraphQLResolveInfo,
    filters: dict[str, list[PullRequestState]] | None = None,
    ordering_direction: OrderingDirection | None = OrderingDirection.DESC,
    **kwargs: Any,
) -> list[Pull]:
    command = info.context["executor"].get_command("pull")
    queryset = await command.fetch_pull_requests(repository, filters)
    return await queryset_to_connection(
        queryset,
        ordering=("pullid",),
        ordering_direction=ordering_direction,
        **kwargs,
    )


# the `requested_fields` here are prefixed with `edges.node`, as this is a `Connection`
# and using `commits { edges { node { ... } } }` is the way this is queried.
STATUS_FIELDS = {"edges.node.coverageStatus", "edges.node.bundleStatus"}


@repository_bindable.field("commits")
async def resolve_commits(
    repository: Repository,
    info: GraphQLResolveInfo,
    filters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> list[Commit]:
    queryset = await sync_to_async(repo_commits)(repository, filters)
    connection = await queryset_to_connection(
        queryset,
        ordering=("timestamp",),
        ordering_direction=OrderingDirection.DESC,
        **kwargs,
    )

    for edge in connection.edges:
        commit = edge["node"]
        # cache all resulting commits in dataloader
        loader = CommitLoader.loader(info, repository.repoid)
        loader.cache(commit)

    requested_fields = selected_fields(info)
    should_load_statuses = not requested_fields.isdisjoint(STATUS_FIELDS)

    if should_load_statuses:
        commit_ids = [edge["node"].id for edge in connection.edges]
        info.context["commit_statuses"] = await sync_to_async(load_commit_statuses)(
            commit_ids
        )

    return connection


@repository_bindable.field("branches")
async def resolve_branches(
    repository: Repository,
    info: GraphQLResolveInfo,
    filters: dict[str, str | bool] | None = None,
    **kwargs: Any,
) -> list[Branch]:
    command = info.context["executor"].get_command("branch")
    queryset = await command.fetch_branches(repository, filters)
    return await queryset_to_connection(
        queryset,
        ordering=("updatestamp",),
        ordering_direction=OrderingDirection.DESC,
        **kwargs,
    )


@repository_bindable.field("defaultBranch")
def resolve_default_branch(repository: Repository, info: GraphQLResolveInfo) -> str:
    return repository.branch


@repository_bindable.field("staticAnalysisToken")
def resolve_static_analysis_token(
    repository: Repository, info: GraphQLResolveInfo
) -> str:
    command = info.context["executor"].get_command("repository")
    return command.get_repository_token(repository, token_type="static_analysis")


@repository_bindable.field("graphToken")
def resolve_graph_token(repository: Repository, info: GraphQLResolveInfo) -> str:
    return repository.image_token


@repository_bindable.field("yaml")
def resolve_repo_yaml(repository: Repository, info: GraphQLResolveInfo) -> str | None:
    if repository.yaml is None:
        return None
    return yaml.dump(repository.yaml)


@repository_bindable.field("bot")
@sync_to_async
def resolve_repo_bot(repository: Repository, info: GraphQLResolveInfo) -> Owner | None:
    return repository.bot


@repository_bindable.field("active")
def resolve_active(repository: Repository, info: GraphQLResolveInfo) -> bool:
    return repository.active or False


@repository_bindable.field("isATSConfigured")
def resolve_is_ats_configured(repository: Repository, info: GraphQLResolveInfo) -> bool:
    if not repository.yaml or "flag_management" not in repository.yaml:
        return False

    # See https://docs.codecov.com/docs/getting-started-with-ats-github-actions on configuring
    # flags. To use Automated Test Selection, a flag is required with Carryforward mode "labels".
    individual_flags = repository.yaml["flag_management"].get("individual_flags", {})
    return individual_flags.get("carryforward_mode") == "labels"


@repository_bindable.field("repositoryConfig")
def resolve_repository_config(
    repository: Repository, info: GraphQLResolveInfo
) -> Repository:
    return repository


@repository_bindable.field("primaryLanguage")
def resolve_language(repository: Repository, info: GraphQLResolveInfo) -> str:
    return repository.language


@repository_bindable.field("languages")
def resolve_languages(repository: Repository, info: GraphQLResolveInfo) -> list[str]:
    return repository.languages


@repository_bindable.field("bundleAnalysisEnabled")
def resolve_bundle_analysis_enabled(
    repository: Repository, info: GraphQLResolveInfo
) -> bool | None:
    return repository.bundle_analysis_enabled


@repository_bindable.field("testAnalyticsEnabled")
def resolve_test_analytics_enabled(
    repository: Repository, info: GraphQLResolveInfo
) -> bool | None:
    return repository.test_analytics_enabled


@repository_bindable.field("coverageEnabled")
def resolve_coverage_enabled(
    repository: Repository, info: GraphQLResolveInfo
) -> bool | None:
    return repository.coverage_enabled


repository_result_bindable = UnionType("RepositoryResult")


@repository_result_bindable.type_resolver
def resolve_repository_result_type(obj: Any, *_: Any) -> str | None:
    if isinstance(obj, Repository):
        return "Repository"
    elif isinstance(obj, OwnerNotActivatedError):
        return "OwnerNotActivatedError"
    elif isinstance(obj, NotFoundError):
        return "NotFoundError"


@repository_bindable.field("isFirstPullRequest")
@sync_to_async
def resolve_is_first_pull_request(
    repository: Repository, info: GraphQLResolveInfo
) -> bool:
    # Get at most 2 PRs to determine if there's only one
    pull_requests = repository.pull_requests.values("id", "compared_to")[:2]
    if len(pull_requests) != 1:
        return False
    # For single PR, check if it's a valid first PR by verifying no compared_to
    return pull_requests[0]["compared_to"] is None


@repository_bindable.field("isGithubRateLimited")
@sync_to_async
def resolve_is_github_rate_limited(
    repository: Repository, info: GraphQLResolveInfo
) -> bool | None:
    if (
        repository.service != SERVICE_GITHUB
        and repository.service != SERVICE_GITHUB_ENTERPRISE
    ):
        return False
    repo_owner = repository.author
    try:
        redis_connection = get_redis_connection()
        rate_limit_redis_key = rate_limits.determine_entity_redis_key(
            owner=repo_owner, repository=repository
        )
        return rate_limits.determine_if_entity_is_rate_limited(
            redis_connection, rate_limit_redis_key
        )
    except Exception:
        log.warning(
            "Error when checking rate limit",
            extra={"repo_id": repository.repoid, "has_owner": bool(repo_owner)},
        )
        return None


@repository_bindable.field("coverageAnalytics")
def resolve_coverage_analytics(
    repository: Repository, info: GraphQLResolveInfo
) -> CoverageAnalyticsProps:
    return CoverageAnalyticsProps(repository=repository)


@repository_bindable.field("testAnalytics")
def resolve_test_analytics(
    repository: Repository,
    info: GraphQLResolveInfo,
) -> Repository:
    """
    resolve_test_analytics defines the data that will get passed to the testAnalytics resolvers
    """
    return repository
