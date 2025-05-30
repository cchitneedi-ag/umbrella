import numbers
from typing import Literal

from database.models.core import Owner
from services.bundle_analysis.notify.types import NotificationType
from shared.bundle_analysis import BundleAnalysisComparison, BundleChange
from shared.django_apps.codecov_auth.models import Service
from shared.torngit.base import TorngitBaseAdapter
from shared.validation.types import BundleThreshold
from shared.yaml import UserYaml


def is_commit_status_configured(
    yaml: UserYaml, owner: Owner
) -> None | NotificationType:
    """Verifies if we should attempt to send bundle analysis commit status based on given YAML.
    Config field is `bundle_analysis.status` (default: "informational")

    If the user is from GitHub and has an app we can send NotificationType.GITHUB_COMMIT_CHECK.
    """
    is_status_configured: bool | Literal["informational"] = yaml.read_yaml_field(
        "bundle_analysis", "status", _else="informational"
    )
    is_github = Service(owner.service) in (Service.GITHUB, Service.GITHUB_ENTERPRISE)
    owner_has_app = owner.github_app_installations != []
    if is_status_configured:
        if is_github and owner_has_app:
            return NotificationType.GITHUB_COMMIT_CHECK
        return NotificationType.COMMIT_STATUS
    return None


def is_comment_configured(yaml: UserYaml, owner: Owner) -> None | NotificationType:
    """Verifies if we should attempt to send bundle analysis PR comment based on given YAML.
    Config field is `comment` (default: see shared.config)
    """
    is_comment_configured: dict | bool = yaml.read_yaml_field("comment") is not False
    if is_comment_configured:
        return NotificationType.PR_COMMENT
    return None


def get_notification_types_configured(
    yaml: UserYaml, owner: Owner
) -> tuple[NotificationType, ...]:
    """Gets a tuple with all the different bundle analysis notifications that we should attempt to send,
    based on the given YAML"""
    notification_types = [
        is_comment_configured(yaml, owner),
        is_commit_status_configured(yaml, owner),
    ]
    return tuple(filter(None, notification_types))


def get_github_app_used(torngit: TorngitBaseAdapter | None) -> int | None:
    if torngit is None:
        return None
    torngit_installation = torngit.data.get("installation")
    selected_installation_id = (
        torngit_installation.get("id") if torngit_installation else None
    )
    return selected_installation_id


def bytes_readable(bytes: int, show_negative: bool | None = True) -> str:
    """Converts bytes into human-readable string (up to GB)"""
    is_negative = bytes < 0
    value: float = abs(bytes)
    exponent_index = 0

    while value >= 1000 and exponent_index < 3:
        value /= 1000
        exponent_index += 1

    exponent_str = [" bytes", "kB", "MB", "GB"][exponent_index]
    rounded_value = round(value, 2)

    if is_negative and show_negative:
        return f"-{rounded_value}{exponent_str}"
    else:
        return f"{rounded_value}{exponent_str}"


def to_BundleThreshold(value: int | float | BundleThreshold) -> BundleThreshold:
    if isinstance(value, list | tuple) and value[0] in ["absolute", "percentage"]:
        return BundleThreshold(*value)
    if isinstance(value, numbers.Integral):
        return BundleThreshold("absolute", value)
    elif isinstance(value, numbers.Number):
        return BundleThreshold("percentage", value)
    raise TypeError(f"Can't parse {value} into BundleThreshold")


def is_bundle_comparison_change_within_configured_threshold(
    comparison: BundleAnalysisComparison,
    threshold: BundleThreshold,
    compare_non_negative_numbers: bool = False,
) -> bool:
    if threshold.type == "absolute":
        total_size_delta = (
            abs(comparison.total_size_delta)
            if compare_non_negative_numbers
            else comparison.total_size_delta
        )
        return total_size_delta <= threshold.threshold
    else:
        return comparison.percentage_delta <= threshold.threshold


def is_bundle_change_within_configured_threshold(
    bundle_change: BundleChange, threshold: BundleThreshold
) -> bool:
    if threshold.type == "absolute":
        return bundle_change.size_delta <= threshold.threshold
    else:
        return bundle_change.percentage_delta <= threshold.threshold
