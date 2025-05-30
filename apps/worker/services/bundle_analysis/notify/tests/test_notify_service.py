from unittest.mock import MagicMock

import pytest

from database.models.core import GITHUB_APP_INSTALLATION_DEFAULT_NAME
from database.tests.factories.core import CommitFactory
from services.bundle_analysis.notify import (
    BundleAnalysisNotifyReturn,
    BundleAnalysisNotifyService,
    NotificationSuccess,
)
from services.bundle_analysis.notify.conftest import (
    get_commit_pair,
    get_enriched_pull_setting_up_mocks,
    get_report_pair,
    save_mock_bundle_analysis_report,
)
from services.bundle_analysis.notify.contexts import (
    BaseBundleAnalysisNotificationContext,
    NotificationContextBuildError,
)
from services.bundle_analysis.notify.contexts.comment import (
    BundleAnalysisPRCommentNotificationContext,
)
from services.bundle_analysis.notify.messages.comment import (
    BundleAnalysisCommentMarkdownStrategy,
)
from services.bundle_analysis.notify.types import NotificationType
from services.notification.notifiers.base import NotificationResult
from shared.config import PATCH_CENTRIC_DEFAULT_CONFIG
from shared.yaml import UserYaml
from tests.helpers import mock_all_plans_and_tiers


def override_comment_builder_and_message_strategy(mocker):
    mock_comment_builder = MagicMock(name="fake_builder")
    mock_comment_builder.get_result.return_value = "D. Context"
    mock_comment_builder.build_context.return_value = mock_comment_builder
    mock_comment_builder.initialize_from_context.return_value = mock_comment_builder
    mock_comment_builder = mocker.patch(
        "services.bundle_analysis.notify.BundleAnalysisPRCommentContextBuilder",
        return_value=mock_comment_builder,
    )
    mock_markdown_strategy = MagicMock(name="fake_markdown_strategy")
    mock_markdown_strategy = mocker.patch(
        "services.bundle_analysis.notify.BundleAnalysisCommentMarkdownStrategy",
        return_value=mock_markdown_strategy,
    )
    mock_comment_builder.return_value.get_result.return_value = MagicMock(
        name="fake_context", notification_type=NotificationType.PR_COMMENT
    )
    mock_markdown_strategy.build_message.return_value = "D. Message"
    mock_markdown_strategy.send_message.return_value = NotificationResult(
        notification_attempted=True,
        notification_successful=True,
        github_app_used=None,
    )
    return (mock_comment_builder, mock_markdown_strategy)


def override_commit_status_builder_and_message_strategy(mocker):
    mock_commit_status_builder = MagicMock(name="fake_commit_status_builder")
    mock_commit_status_builder.get_result.return_value = "D. Context"
    mock_commit_status_builder.build_context.return_value = mock_commit_status_builder
    mock_commit_status_builder.initialize_from_context.return_value = (
        mock_commit_status_builder
    )
    mock_commit_status_builder = mocker.patch(
        "services.bundle_analysis.notify.CommitStatusNotificationContextBuilder",
        return_value=mock_commit_status_builder,
    )
    commit_status_message_strategy = MagicMock(name="fake_markdown_strategy")
    commit_status_message_strategy = mocker.patch(
        "services.bundle_analysis.notify.CommitStatusMessageStrategy",
        return_value=commit_status_message_strategy,
    )
    mock_commit_status_builder.return_value.get_result.return_value = MagicMock(
        name="fake_context", notification_type=NotificationType.COMMIT_STATUS
    )
    commit_status_message_strategy.build_message.return_value = "D. Message"
    commit_status_message_strategy.send_message.return_value = NotificationResult(
        notification_attempted=True,
        notification_successful=True,
        github_app_used=None,
    )
    return (mock_commit_status_builder, commit_status_message_strategy)


@pytest.fixture
def mock_base_context():
    context_requirements = (
        CommitFactory(),
        GITHUB_APP_INSTALLATION_DEFAULT_NAME,
    )
    context = BaseBundleAnalysisNotificationContext(*context_requirements)
    context.commit_report = MagicMock(name="fake_CommitReport")
    context.bundle_analysis_report = MagicMock(name="fake_BundleAnalysisReport")
    return context


class TestCreateContextForNotification:
    def test_build_base_context(self, mocker, dbsession, mock_storage):
        head_commit, base_commit = get_commit_pair(dbsession)
        head_commit_report, _ = get_report_pair(dbsession, (head_commit, base_commit))
        save_mock_bundle_analysis_report(
            head_commit.repository,
            head_commit_report,
            mock_storage,
            sample_report_number=1,
        )
        service = BundleAnalysisNotifyService(
            head_commit, UserYaml.from_dict(PATCH_CENTRIC_DEFAULT_CONFIG)
        )
        base_context = service.build_base_context()
        assert base_context.commit_report == head_commit_report
        assert base_context.bundle_analysis_report.session_count() == 19

    @pytest.mark.django_db
    def test_create_context_success(self, dbsession, mock_storage, mocker):
        mock_all_plans_and_tiers()
        current_yaml = UserYaml.from_dict(PATCH_CENTRIC_DEFAULT_CONFIG)
        head_commit, base_commit = get_commit_pair(dbsession)
        head_commit_report, base_commit_report = get_report_pair(
            dbsession, (head_commit, base_commit)
        )
        save_mock_bundle_analysis_report(
            head_commit.repository,
            head_commit_report,
            mock_storage,
            sample_report_number=1,
        )
        save_mock_bundle_analysis_report(
            head_commit.repository,
            base_commit_report,
            mock_storage,
            sample_report_number=2,
        )
        enriched_pull = get_enriched_pull_setting_up_mocks(
            dbsession, mocker, (head_commit, base_commit)
        )
        service = BundleAnalysisNotifyService(head_commit, current_yaml)
        result = service.create_context_for_notification(
            BaseBundleAnalysisNotificationContext(
                head_commit, GITHUB_APP_INSTALLATION_DEFAULT_NAME
            ),
            NotificationType.PR_COMMENT,
        )
        assert result is not None
        assert isinstance(
            result.notification_context, BundleAnalysisPRCommentNotificationContext
        )
        assert isinstance(
            result.message_strategy, BundleAnalysisCommentMarkdownStrategy
        )
        context = result.notification_context
        assert context.commit_report == head_commit_report
        assert context.bundle_analysis_report.session_count() == 19
        assert context.pull == enriched_pull
        assert (
            context.bundle_analysis_comparison.base_report_key
            == base_commit_report.external_id
        )
        assert (
            context.bundle_analysis_comparison.head_report_key
            == head_commit_report.external_id
        )

    def test_create_contexts_unknown_notification(self, mock_base_context):
        current_yaml = UserYaml.from_dict({})
        service = BundleAnalysisNotifyService(mock_base_context.commit, current_yaml)
        assert (
            service.create_context_for_notification(
                mock_base_context, "unknown_notification_type"
            )
            is None
        )

    def test_create_context_for_notification_build_fails(
        self, mocker, mock_base_context
    ):
        mock_comment_builder = MagicMock(name="fake_builder")
        mock_comment_builder.initialize_from_context.return_value = mock_comment_builder
        mock_comment_builder.build_context.side_effect = NotificationContextBuildError(
            "mock_failed_step"
        )
        current_yaml = UserYaml.from_dict({})
        mock_comment_builder = mocker.patch(
            "services.bundle_analysis.notify.BundleAnalysisPRCommentContextBuilder",
            return_value=mock_comment_builder,
        )
        service = BundleAnalysisNotifyService(mock_base_context.commit, current_yaml)
        assert (
            service.create_context_for_notification(
                mock_base_context, NotificationType.PR_COMMENT
            )
            is None
        )


class TestBundleAnalysisNotifyService:
    def test_skip_all_notification_base_context_failed(
        self, mocker, dbsession, mock_storage, caplog
    ):
        head_commit, _ = get_commit_pair(dbsession)
        service = BundleAnalysisNotifyService(
            head_commit,
            UserYaml.from_dict({"comment": {"require_bundle_changes": False}}),
        )
        result = service.notify()
        warning_logs = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert any(
            warning.message == "Failed to build NotificationContext"
            for warning in warning_logs
        )
        assert any(
            warning.message
            == "Skipping ALL notifications because there's no base context"
            for warning in warning_logs
        )
        assert result == BundleAnalysisNotifyReturn(
            notifications_configured=(
                NotificationType.PR_COMMENT,
                NotificationType.COMMIT_STATUS,
            ),
            notifications_attempted=(),
            notifications_successful=(),
        )

    @pytest.mark.parametrize(
        "current_yaml, expected_configured_count, expected_success_count",
        [
            pytest.param(
                {
                    "comment": {"require_bundle_changes": False},
                    "bundle_analysis": {"status": "informational"},
                },
                2,
                2,
                id="comment_and_status",
            ),
            pytest.param(
                {
                    "comment": {"require_bundle_changes": False},
                    "bundle_analysis": {"status": False},
                },
                1,
                1,
                id="only_comment_sent",
            ),
            pytest.param(
                {
                    "comment": False,
                },
                1,
                1,
                id="only_commit_status",
            ),
        ],
    )
    def test_notify(
        self,
        current_yaml,
        expected_configured_count,
        expected_success_count,
        mocker,
        mock_base_context,
    ):
        override_comment_builder_and_message_strategy(mocker)
        override_commit_status_builder_and_message_strategy(mocker)

        mocker.patch.object(
            BundleAnalysisNotifyService,
            "build_base_context",
            return_value=mock_base_context,
        )
        current_yaml = UserYaml.from_dict(current_yaml)
        mock_base_context.current_yaml = current_yaml
        service = BundleAnalysisNotifyService(mock_base_context.commit, current_yaml)
        result = service.notify()
        assert len(result.notifications_configured) == expected_configured_count
        assert len(result.notifications_successful) == expected_success_count

    @pytest.mark.parametrize(
        "result, success_value",
        [
            (
                BundleAnalysisNotifyReturn([], [], []),
                NotificationSuccess.NOTHING_TO_NOTIFY,
            ),
            (
                BundleAnalysisNotifyReturn(
                    [NotificationType.COMMIT_STATUS],
                    [NotificationType.COMMIT_STATUS],
                    [NotificationType.COMMIT_STATUS],
                ),
                NotificationSuccess.FULL_SUCCESS,
            ),
            (
                BundleAnalysisNotifyReturn(
                    [NotificationType.COMMIT_STATUS, NotificationType.PR_COMMENT],
                    [NotificationType.COMMIT_STATUS, NotificationType.PR_COMMENT],
                    [NotificationType.COMMIT_STATUS],
                ),
                NotificationSuccess.PARTIAL_SUCCESS,
            ),
        ],
    )
    def test_to_NotificationSuccess(self, result, success_value):
        assert result.to_NotificationSuccess() == success_value
