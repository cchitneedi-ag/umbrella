import os

from helpers.sentry import initialize_sentry


class TestSentry:
    def test_initialize_sentry(self, mocker, mock_configuration):
        mock_configuration._params["services"] = {"sentry": {"server_dsn": "this_dsn"}}
        cluster = "test_env"
        mocker.patch.dict(
            os.environ,
            {"RELEASE_VERSION": "FAKE_VERSION_FOR_YOU", "CLUSTER_ENV": cluster},
        )
        mocked_init = mocker.patch("helpers.sentry.sentry_sdk.init")
        mocked_set_tag = mocker.patch("helpers.sentry.sentry_sdk.set_tag")
        assert initialize_sentry() is None
        mocked_init.assert_called_with(
            "this_dsn",
            release="worker-FAKE_VERSION_FOR_YOU",
            sample_rate=1.0,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment="production",
            _experiments=mocker.ANY,
            integrations=mocker.ANY,
        )
        mocked_set_tag.assert_called_with("cluster", cluster)
