import logging
from typing import Any

from shared.bots.github_apps import get_github_app_info_for_owner
from shared.bots.owner_bots import get_owner_appropriate_bot_token
from shared.bots.public_bots import get_token_type_mapping
from shared.bots.repo_bots import get_repo_appropriate_bot_token
from shared.bots.types import AdapterAuthInformation
from shared.django_apps.codecov_auth.models import (
    GITHUB_APP_INSTALLATION_DEFAULT_NAME,
    Owner,
    Service,
)
from shared.django_apps.core.models import Repository
from shared.typings.torngit import GithubInstallationInfo

log = logging.getLogger(__name__)

SQLAlchemyOwner = Any
SQLAlchemyRepository = Any


def get_adapter_auth_information(
    owner: Owner | SQLAlchemyOwner,
    repository: Repository | SQLAlchemyRepository | None = None,
    *,
    ignore_installations: bool = False,
    installation_name_to_use: str = GITHUB_APP_INSTALLATION_DEFAULT_NAME,
) -> AdapterAuthInformation:
    """
    Gets all the auth information needed to send requests to the provider.
    This logic is used by the worker to get the data needed to create a torngit.BaseAdapter.
    :warning: Api should use the `owner.oauth_token` of the user making the request.
    """
    installation_info: GithubInstallationInfo | None = None
    token_type_mapping = None
    fallback_installations: list[GithubInstallationInfo] | None = None
    if (
        Service(owner.service) in [Service.GITHUB, Service.GITHUB_ENTERPRISE]
        # in sync_teams and sync_repos we might prefer to use the owner's OAuthToken instead of installation
        and not ignore_installations
    ):
        installations_available_info = get_github_app_info_for_owner(
            owner,
            repository=repository,
            installation_name=installation_name_to_use,
        )
        if installations_available_info != []:
            installation_info, *fallback_installations = installations_available_info

    if repository:
        token, token_owner = get_repo_appropriate_bot_token(
            repository, installation_info
        )
        if installation_info is None:
            # the admin_bot_token should be associated with an Owner so we know that it was
            # actually configured for this Repository.
            # The exception would be GH installation tokens, but in that case we don't use token_type_mapping
            token_type_mapping = get_token_type_mapping(
                repository, admin_bot_token=(token if token_owner else None)
            )
    else:
        token, token_owner = get_owner_appropriate_bot_token(owner, installation_info)
    return AdapterAuthInformation(
        token=token,
        token_owner=token_owner,
        selected_installation_info=installation_info,
        fallback_installations=fallback_installations,
        token_type_mapping=token_type_mapping,
    )
