import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from shared.analytics_tracking import get_list_of_analytic_tools, get_tools_manager
from shared.analytics_tracking.events import Event, Events
from shared.analytics_tracking.manager import AnalyticsToolManager
from shared.analytics_tracking.marketo import Marketo
from shared.analytics_tracking.pubsub import CustomJSONEncoder, PubSub
from shared.config import ConfigHelper


@pytest.fixture
def mock_pubsub():
    with patch("shared.analytics_tracking.PubSub.is_enabled", return_value=True):
        yield


@pytest.fixture
def mock_marketo():
    with patch("shared.analytics_tracking.Marketo.is_enabled", return_value=True):
        yield


@pytest.fixture
def mock_pubsub_publisher():
    with patch(
        "shared.analytics_tracking.pubsub.pubsub_v1.PublisherClient"
    ) as mock_publisher_client:
        mock_publisher = mock_publisher_client.return_value
        mock_publisher.topic_path.return_value = "projects/1234/topics/codecov"
        yield mock_publisher


def test_get_list_of_analytic_tools():
    tools = get_list_of_analytic_tools()
    assert isinstance(tools, list)


def test_get_tools_manager(mock_pubsub):
    tool = get_tools_manager()
    assert tool is not None
    assert isinstance(tool, AnalyticsToolManager)


def test_track_event(mock_pubsub, mock_marketo, mock_pubsub_publisher, mocker):
    analytics_tool = get_tools_manager()
    mock_marketo_request = mocker.patch(
        "shared.analytics_tracking.Marketo.make_rest_request"
    )
    event = Event(
        Events.USER_SIGNED_IN.value,
        test=True,
    )
    mocker.patch("shared.analytics_tracking.manager.Event", return_value=event)
    analytics_tool.track_event(
        Events.USER_SIGNED_IN.value,
        is_enterprise=False,
        event_data={"test": True},
    )

    mock_pubsub_publisher.publish.assert_called_with(
        "projects/1234/topics/codecov",
        data=json.dumps(event.serialize()).encode("utf-8"),
    )
    mock_marketo_request.assert_called_with(
        Marketo.LEAD_URL,
        method="POST",
        json={
            "input": [event.serialize()],
        },
    )


def test_track_event_tool_not_enabled(mocker, mock_pubsub_publisher):
    analytics_tool = get_tools_manager()

    analytics_tool.track_event(
        Events.USER_SIGNED_UP.value,
        is_enterprise=False,
        event_data={"test": True},
    )

    mock_pubsub_publisher.publish.assert_not_called()


def test_track_event_invalid_name(mocker, mock_pubsub_publisher):
    analytics_tool = get_tools_manager()
    with pytest.raises(ValueError):
        analytics_tool.track_event(
            "Invalid Name", is_enterprise=False, event_data={"test": True}
        )
    mock_pubsub_publisher.publish.assert_not_called()


def test_track_event_is_enterprise(mock_pubsub_publisher, mocker):
    analytics_tool = get_tools_manager()
    analytics_tool.track_event(
        "codecov.account.uploaded_coverage_report",
        is_enterprise=True,
        event_data={"test": True},
    )
    mock_pubsub_publisher.publish.assert_not_called()


class TestPubSub:
    def test_pubsub_enabled(self, mocker):
        yaml_content = "\n".join(
            [
                "setup:",
                "  pubsub:",
                "    enabled: true",
            ]
        )
        mocker.patch.object(ConfigHelper, "load_yaml_file", return_value=yaml_content)
        this_config = ConfigHelper()
        mocker.patch("shared.config._get_config_instance", return_value=this_config)
        assert PubSub.is_enabled()

    def test_pubsub_not_enabled(self, mocker):
        yaml_content = "\n".join(
            [
                "setup:",
                "  pubsub:",
                "    enabled: false",
            ]
        )
        mocker.patch.object(ConfigHelper, "load_yaml_file", return_value=yaml_content)
        this_config = ConfigHelper()
        mocker.patch("shared.config._get_config_instance", return_value=this_config)
        assert not PubSub.is_enabled()

    def test_pubsub_initialized(self, mocker, mock_pubsub_publisher):
        yaml_content = "\n".join(
            [
                "setup:",
                "  pubsub:",
                "    enabled: true",
                "    project_id: '1234'",
                "    topic: codecov",
            ]
        )
        mocker.patch.object(ConfigHelper, "load_yaml_file", return_value=yaml_content)
        this_config = ConfigHelper()
        mocker.patch("shared.config._get_config_instance", return_value=this_config)
        pubsub = PubSub()
        assert pubsub.topic == "projects/1234/topics/codecov"
        assert pubsub.project == "1234"

    def test_pubsub_track_event(self, mocker, mock_pubsub_publisher, mock_pubsub):
        event = Event(
            Events.ACCOUNT_ACTIVATED_REPOSITORY.value,
            user_id="1234",
            repo_id="1234",
            branch="test_branch",
        )
        pubsub = PubSub()
        pubsub.track_event(event)
        mock_pubsub_publisher.publish.assert_called_with(
            pubsub.topic, data=json.dumps(event.serialize()).encode("utf-8")
        )

    def test_pubsub_track_event_with_datetime(
        self, mocker, mock_pubsub_publisher, mock_pubsub
    ):
        other_timestamp = datetime(2023, 9, 12, tzinfo=UTC)
        event = Event(
            event_name=Events.ACCOUNT_ACTIVATED_REPOSITORY.value,
            other_timestamp=other_timestamp,
            user_id="1234",
            repo_id="1234",
            branch="test_branch",
        )
        pubsub = PubSub()
        pubsub.track_event(event)
        serialized_event = json.dumps(event.serialize(), cls=CustomJSONEncoder).encode(
            "utf-8"
        )
        mock_pubsub_publisher.publish.assert_called_with(
            pubsub.topic, data=serialized_event
        )


class TestEvent:
    def test_event(self, mocker):
        class uuid:
            bytes = b"\x00\x01\x02"

        mocker.patch("shared.analytics_tracking.events.uuid1", return_value=uuid)
        event = Event(
            Events.ACCOUNT_ACTIVATED_REPOSITORY.value,
            dt=datetime(2023, 9, 12, tzinfo=UTC),
            user_id="1234",
            repo_id="1234",
            branch="test_branch",
        )
        assert event.serialize() == {
            "uuid": "AAEC",
            "timestamp": 1694476800.0,
            "type": "codecov.account.activated_repository",
            "data": {"user_id": "1234", "repo_id": "1234", "branch": "test_branch"},
        }

    def test_invalid_event(self, mocker):
        with pytest.raises(ValueError, match="Invalid event name: Invalid name"):
            Event(
                "Invalid name",
                dt=datetime(2023, 9, 12, tzinfo=UTC),
                user_id="1234",
                repo_id="1234",
                branch="test_branch",
            )
