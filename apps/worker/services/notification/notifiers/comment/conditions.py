import logging
from abc import ABC, abstractmethod
from decimal import Decimal

from services.comparison import ComparisonProxy
from services.notification.notifiers.base import (
    AbstractBaseNotifier,
    NotificationResult,
)
from services.yaml import read_yaml_field
from shared.validation.types import (
    CoverageCommentRequiredChanges,
    CoverageCommentRequiredChangesORGroup,
)

log = logging.getLogger(__name__)


class NotifyCondition(ABC):
    """Abstract class that defines the basis of a NotifyCondition.

    NotifyCondition specifies the conditions that need to be met in order for a notification to be sent
    from Codecov to a git provider.
    NotifyCondition can have a side effect that is called when the condition fails.
    """

    failure_explanation: str

    @staticmethod
    @abstractmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        return True

    @staticmethod
    def on_failure_side_effect(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> NotificationResult:
        return NotificationResult()


class ComparisonHasPull(NotifyCondition):
    failure_explanation = "no_pull_request"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        return comparison.pull is not None


class PullRequestInProvider(NotifyCondition):
    failure_explanation = "pull_request_not_in_provider"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        return (
            comparison.enriched_pull is not None
            and comparison.enriched_pull.provider_pull is not None
        )


class PullRequestOpen(NotifyCondition):
    failure_explanation = "pull_request_closed"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        return comparison.pull.state == "open"


class PullHeadMatchesComparisonHead(NotifyCondition):
    failure_explanation = "pull_head_does_not_match"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        return comparison.pull.head == comparison.head.commit.commitid


class HasEnoughBuilds(NotifyCondition):
    failure_explanation = "not_enough_builds"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        expected_builds = notifier.notifier_yaml_settings.get("after_n_builds", 0)
        present_builds = len(comparison.head.report.sessions)
        return present_builds >= expected_builds


class HasEnoughRequiredChanges(NotifyCondition):
    failure_explanation = "changes_required"

    @staticmethod
    def _check_unexpected_changes(comparison: ComparisonProxy) -> bool:
        """Returns a bool that indicates wether there are unexpected changes"""
        return bool(comparison.get_changes())

    @staticmethod
    def _check_coverage_change(comparison: ComparisonProxy) -> bool:
        """Returns a bool that indicates wether there is any change in coverage"""
        diff = comparison.get_diff()
        res = None if diff is None else comparison.head.report.calculate_diff(diff)
        return res is not None and res["general"].lines > 0

    @staticmethod
    def _check_any_change(comparison: ComparisonProxy) -> bool:
        unexpected_changes = HasEnoughRequiredChanges._check_unexpected_changes(
            comparison
        )
        coverage_changes = HasEnoughRequiredChanges._check_coverage_change(comparison)
        return unexpected_changes or coverage_changes

    @staticmethod
    def _check_coverage_drop(comparison: ComparisonProxy) -> bool:
        no_head_coverage = comparison.head.report.totals.coverage is None
        no_base_report = comparison.project_coverage_base.report is None
        no_base_coverage = (
            no_base_report
            or comparison.project_coverage_base.report.totals.coverage is None
        )
        if no_head_coverage or no_base_coverage:
            # We don't know if there was a coverage drop, because we can't compare BASE and HEAD (missing some info)
            # But we default to showing the comment. It might have info for the user about _what_ info we are missing
            return True
        head_coverage = Decimal(comparison.head.report.totals.coverage).quantize(
            Decimal("0.00000")
        )
        project_status_config = read_yaml_field(
            comparison.comparison.current_yaml, ("coverage", "status", "project"), {}
        )
        threshold = 0
        if isinstance(project_status_config, dict):
            # Project status can also be a bool value, so check is needed
            threshold = Decimal(project_status_config.get("threshold", 0))
        target_coverage = Decimal(
            comparison.project_coverage_base.report.totals.coverage
        ).quantize(Decimal("0.00000"))
        diff = head_coverage - target_coverage
        # Need to take the project threshold into consideration
        return diff < 0 and abs(diff) >= (threshold + Decimal(0.01))

    @staticmethod
    def _check_uncovered_patch(comparison: ComparisonProxy) -> bool:
        diff = comparison.get_diff(use_original_base=True)
        totals = None if diff is None else comparison.head.report.apply_diff(diff)
        coverage_not_affected_by_patch = totals and totals.lines == 0
        if totals is None or coverage_not_affected_by_patch:
            # The patch doesn't affect coverage. So we don't show a comment.
            # The patch is probably not related to testable files
            return False
        coverage = Decimal(totals.coverage).quantize(Decimal("0.00000"))
        return abs(coverage - Decimal(100).quantize(Decimal("0.00000"))) >= Decimal(
            0.01
        )

    @staticmethod
    def check_condition_OR_group(
        condition_group: CoverageCommentRequiredChangesORGroup,
        comparison: ComparisonProxy,
    ) -> bool:
        if condition_group == CoverageCommentRequiredChanges.no_requirements.value:
            return True
        cache_results = dict.fromkeys(CoverageCommentRequiredChanges)
        functions_lookup = {
            CoverageCommentRequiredChanges.any_change: HasEnoughRequiredChanges._check_any_change,
            CoverageCommentRequiredChanges.coverage_drop: HasEnoughRequiredChanges._check_coverage_drop,
            CoverageCommentRequiredChanges.uncovered_patch: HasEnoughRequiredChanges._check_uncovered_patch,
        }
        final_result = False
        for individual_condition in CoverageCommentRequiredChanges:
            if condition_group & individual_condition.value:
                if cache_results[individual_condition] is None:
                    function_to_call = functions_lookup[individual_condition]
                    cache_results[individual_condition] = function_to_call(comparison)
                final_result |= cache_results[individual_condition]
        return final_result

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        if comparison.pull and comparison.pull.commentid:
            log.info(
                "Comment already exists. Skipping required_changes verification to update comment",
                extra={"pull": comparison.pull.pullid, "commit": comparison.pull.head},
            )
            return True
        required_changes = notifier.notifier_yaml_settings.get(
            "require_changes", [CoverageCommentRequiredChanges.no_requirements.value]
        )
        # backwards compatibility (can be removed after full rollout)
        if isinstance(required_changes, bool):
            # True --> 1 (any_change)
            # False --> 0 (no_requirements)
            required_changes = [int(required_changes)]
        return all(
            HasEnoughRequiredChanges.check_condition_OR_group(or_group, comparison)
            for or_group in required_changes
        )


class NoAutoActivateMessageIfAutoActivateIsOff(NotifyCondition):
    failure_explanation = "auto_activate_message_but_auto_activate_is_off"

    @staticmethod
    def check_condition(
        notifier: AbstractBaseNotifier, comparison: ComparisonProxy
    ) -> bool:
        owner = notifier.repository.owner
        # Return False ONLY if (owner.plan_auto_activate is False) and should_use_upgrade_message
        # Checking if owner.plan_auto_activate is False so None will pass (tests)
        return (owner.plan_auto_activate != False) or (
            not notifier.should_use_upgrade_decoration()
        )
