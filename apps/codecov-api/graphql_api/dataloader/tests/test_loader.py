import pytest
from django.test import TestCase

from graphql_api.dataloader.loader import BaseLoader
from shared.django_apps.core.tests.factories import CommitFactory


class GraphQLResolveInfo:
    def __init__(self):
        self.context = {}


class BaseLoaderTestCase(TestCase):
    def setUp(self):
        # record type is irrelevant here
        self.record = CommitFactory(message="test commit", commitid="123")

        self.info = GraphQLResolveInfo()

    async def test_unimplemented_load(self):
        loader = BaseLoader.loader(self.info)
        with pytest.raises(NotImplementedError):
            await loader.load(self.record.id)

    async def test_default_key(self):
        key = BaseLoader.key(self.record)
        assert key == self.record.id
