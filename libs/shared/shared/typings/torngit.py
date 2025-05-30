from typing import NotRequired, TypedDict

from shared.reports.types import UploadType


class OwnerInfo(TypedDict):
    service_id: str
    ownerid: int | None
    username: str


class RepoInfo(TypedDict):
    name: str
    using_integration: bool
    service_id: str
    repoid: int
    private: bool | None


class GithubInstallationInfo(TypedDict):
    """
    Information about a Github installation.
    `id` - The id of the GithubAppInstallation object in the database
           If using the deprecated owner.integration_id it doesn't exist.
    `installation_id` - Required info to get a token from Github for a given installation.
    """

    id: NotRequired[int]
    installation_id: int
    # The default app (configured via yaml) doesn't need `app_id` and `pem_path`.
    # All other apps need `app_id` and `pem_path`.
    app_id: NotRequired[int | None]
    pem_path: NotRequired[str | None]


class AdditionalData(TypedDict):
    upload_type: NotRequired[UploadType]


class TorngitInstanceData(TypedDict):
    owner: OwnerInfo | dict
    repo: RepoInfo | dict
    fallback_installations: list[GithubInstallationInfo | None] | None
    installation: GithubInstallationInfo | None
    additional_data: AdditionalData | None
