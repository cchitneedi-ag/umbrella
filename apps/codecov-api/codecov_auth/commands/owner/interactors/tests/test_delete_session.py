import pytest
from asgiref.sync import sync_to_async
from django.test import TestCase

from codecov.commands.exceptions import Unauthenticated
from codecov_auth.models import DjangoSession, Session
from codecov_auth.tests.factories import DjangoSessionFactory
from shared.django_apps.codecov_auth.tests.factories import OwnerFactory, SessionFactory

from ..delete_session import DeleteSessionInteractor


@sync_to_async
def get_session(id):
    return Session.objects.get(sessionid=id)


class DeleteSessionInteractorTest(TestCase):
    def setUp(self):
        self.owner = OwnerFactory(username="codecov-user")
        self.django_session = DjangoSessionFactory()
        self.session = SessionFactory(
            owner=self.owner, login_session=self.django_session
        )

    async def test_when_unauthenticated_raise(self):
        with pytest.raises(Unauthenticated):
            await DeleteSessionInteractor(None, "github").execute(12)

    async def test_delete_session(self):
        await DeleteSessionInteractor(self.owner, "github").execute(
            self.session.sessionid
        )

        @sync_to_async
        def assert_sessions():
            return (
                len(DjangoSession.objects.all()) == 0
                and len(Session.objects.all()) == 0
            )

        assert assert_sessions
