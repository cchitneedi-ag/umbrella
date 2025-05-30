import logging

from shared.bots.exceptions import (
    OwnerWithoutValidBotError,
    RepositoryWithoutValidBotError,
)
from shared.bots.github_apps import get_github_app_token
from shared.bots.owner_bots import get_owner_or_appropriate_bot
from shared.bots.public_bots import get_public_bot_token
from shared.bots.types import TokenWithOwner
from shared.config import get_config
from shared.django_apps.codecov_auth.models import Owner, Service
from shared.django_apps.core.models import Repository
from shared.encryption.oauth import get_encryptor_from_configuration
from shared.environment.environment import is_enterprise
from shared.orms.repository_helper import DjangoSQLAlchemyRepositoryWrapper
from shared.rate_limits import owner_key_name
from shared.typings.torngit import GithubInstallationInfo

encryptor = get_encryptor_from_configuration()

log = logging.getLogger(__name__)


def get_repo_particular_bot_token(repo) -> TokenWithOwner:
    appropriate_bot = get_repo_appropriate_bot(repo)
    token_dict = encryptor.decrypt_token(appropriate_bot.oauth_token)
    token_dict["username"] = appropriate_bot.username
    token_dict["entity_name"] = owner_key_name(appropriate_bot.ownerid)
    return token_dict, appropriate_bot


def get_repo_appropriate_bot(repo: Repository) -> Owner:
    if repo.bot is not None and repo.bot.oauth_token is not None:
        log.info(
            "Repo has specific bot",
            extra={"repoid": repo.repoid, "botid": repo.bot.ownerid},
        )
        return repo.bot
    try:
        return get_owner_or_appropriate_bot(
            DjangoSQLAlchemyRepositoryWrapper.get_repo_owner(repo)
        )
    except OwnerWithoutValidBotError:
        raise RepositoryWithoutValidBotError()


def get_repo_appropriate_bot_token(
    repo: Repository,
    installation_info: GithubInstallationInfo | None = None,
) -> TokenWithOwner:
    extra_info_to_log = {
        "repoid": repo.repoid,
        "is_private": repo.private,
        "service": repo.service,
    }
    log.info(
        "Get repo appropriate bot token",
        extra={"installation_info": installation_info, **extra_info_to_log},
    )

    service = Service(repo.service)

    if is_enterprise() and get_config(repo.service, "bot"):
        log.info(
            "Using enterprise-configured bot for the service", extra=extra_info_to_log
        )
        return get_public_bot_token(service, repo.repoid)

    if installation_info:
        log.info("Using github installation", extra=extra_info_to_log)
        return get_github_app_token(service, installation_info)
    try:
        token_dict, appropriate_bot = get_repo_particular_bot_token(repo)
        log.info("Using repo particular bot", extra=extra_info_to_log)
        return token_dict, appropriate_bot
    except RepositoryWithoutValidBotError as e:
        if not repo.private:
            log.info("Using YAML-configured public bot", extra=extra_info_to_log)
            return get_public_bot_token(service, repo.repoid)
        raise e
