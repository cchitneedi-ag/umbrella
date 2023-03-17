from ariadne import UnionType

from graphql_api.helpers.mutation import (
    resolve_union_error_type,
    wrap_error_handling_mutation,
)


@wrap_error_handling_mutation
async def resolve_regenerate_profling_token(_, info, input):
    command = info.context["executor"].get_command("repository")
    profilingToken = await command.regenerate_repository_token(
        repo_name=input.get("repoName"),
        owner_username=input.get("owner"),
        token_type="profiling",
    )
    return {"profiling_token": profilingToken}


error_generate_profiling_token = UnionType("RegenerateProfilingTokenError")
error_generate_profiling_token.type_resolver(resolve_union_error_type)
