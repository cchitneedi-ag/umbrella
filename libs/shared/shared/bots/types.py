from typing import Any, TypedDict

from shared.django_apps.codecov_auth.models import Owner
from shared.torngit.base import TokenType
from shared.typings.oauth_token_types import Token
from shared.typings.torngit import GithubInstallationInfo

# A Token and its Owner
# If a Token doesn't belong to Owner (i.e. it's a GitHubAppInstallation Token), second value is None
TokenWithOwner = tuple[Token, Owner | None]

TokenTypeMapping = dict[TokenType, Token]


class AdapterAuthInformation(TypedDict):
    """This class is just a type annotation for the return value of services.bots.get_adapter_auth_information
    It is a container with all the information we need to authenticate a given repo/owner with the git provider.
    Specific fields have comments to document them further
    """

    # This is the Authentication used with the git provider
    token: Token
    # token_owner is used to decide on token_refresh functions. Could be SQLAlchemy | Django Owner - leaving Any here
    token_owner: Owner | Any | None
    # GitHub app info - exclusive for GitHub (duh)
    # Preferred method of authentication (if available)
    # selected_installation_info is the installation being used to communicate with github. We save this info in the TorngitAdapter.
    #   If this installation becomes rate-limited the TorngitAdapter uses the info to mark it so (so we don't select it for a while)
    # fallback_installations are used if multi-apps are available and the selected one becomes rate-limited
    selected_installation_info: GithubInstallationInfo | None
    fallback_installations: list[GithubInstallationInfo] | None
    # TokenTypeMapping
    # exclusive for public repos not using an installation. Fallback tokens per action
    token_type_mapping: TokenTypeMapping | None
