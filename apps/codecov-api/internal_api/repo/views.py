import uuid
import logging
from datetime import datetime

from rest_framework import filters, mixins, viewsets
from rest_framework.exceptions import PermissionDenied, NotAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS # ['GET', 'HEAD', 'OPTIONS']
from rest_framework import status

from django_filters import rest_framework as django_filters, BooleanFilter
from internal_api.repo.filter import RepositoryFilters, RepositoryOrderingFilter

from core.models import Repository
from services.repo_providers import RepoProviderService
from services.segment import SegmentService
from services.decorators import torngit_safe
from internal_api.permissions import RepositoryPermissionsService
from internal_api.mixins import OwnerPropertyMixin

from .repository_accessors import RepoAccessors
from .serializers import (
    RepoWithMetricsSerializer,
    RepoDetailsSerializer,
    SecretStringPayloadSerializer,
)

from .utils import encode_secret_string

from .repository_actions import delete_webhook_on_provider, create_webhook_on_provider


log = logging.getLogger(__name__)


class RepositoryViewSet(
        mixins.ListModelMixin,
        mixins.RetrieveModelMixin,
        mixins.UpdateModelMixin,
        mixins.DestroyModelMixin,
        viewsets.GenericViewSet,
        OwnerPropertyMixin
    ):

    filter_backends = (
        django_filters.DjangoFilterBackend,
        filters.SearchFilter,
        RepositoryOrderingFilter
    )
    filterset_class = RepositoryFilters
    search_fields = ('name',)
    ordering_fields = (
        'updatestamp',
        'name',
        'latest_coverage_change',
        'coverage',
        'lines',
        'hits',
        'partials',
        'misses',
        'complexity',
    )
    lookup_value_regex = '[\w\.@\:\-~]+'
    lookup_field = 'repo_name'
    accessors = RepoAccessors()

    def _assert_is_admin(self):
        if not self.owner.is_admin(self.request.user):
            raise PermissionDenied()

    def get_serializer_class(self):
        if self.action == 'list':
            return RepoWithMetricsSerializer
        return RepoDetailsSerializer

    def get_serializer_context(self, *args, **kwargs):
        context = super().get_serializer_context(*args, **kwargs)
        if self.action != 'list':
            context.update({"can_edit": self.can_edit, "can_view": self.can_view})
        return context

    def get_queryset(self):
        queryset = self.owner.repository_set.viewable_repos(
            self.request.user
        ).select_related(
            "author"
        )

        if self.action == 'list':
            if self.request.query_params.get("exclude_uncovered", False):
                queryset = queryset.exclude_uncovered()

            queryset = queryset.with_latest_commit_totals_before(
                self.request.query_params.get("before_date", datetime.now().isoformat()),
                self.request.query_params.get("branch", None),
                include_previous_totals=True
            ).with_latest_coverage_change()

        return queryset

    @torngit_safe
    def check_object_permissions(self, request, repo):
        # Below is some hacking to avoid requesting permissions from API in certain scenarios.
        if not request.user.is_authenticated and not repo.private:
            # Unauthenticated users only have read-access to public repositories,
            # so we avoid this API call here
            self.can_view, self.can_edit = True, False
        elif not request.user.is_authenticated and repo.private:
            raise NotAuthenticated(detail="You must be logged in to view private repository data.")
        else:
            # If the user is authenticated, we can fetch permissions from the provider
            # to determine write permissions.
            self.can_view, self.can_edit = self.accessors.get_repo_permissions(self.request.user, repo)

        if repo.private and not RepositoryPermissionsService().user_is_activated(self.request.user, self.owner):
            raise PermissionDenied("User not activated")
        if self.request.method not in SAFE_METHODS and not self.can_edit:
            raise PermissionDenied()
        if self.request.method == 'DELETE':
            self._assert_is_admin()
        if not self.can_view:
            raise PermissionDenied()

    @torngit_safe
    def get_object(self):
        # Get request args and try to find the repo in the DB
        repo_name = self.kwargs.get('repo_name')
        org_name = self.kwargs.get('owner_username')
        service = self.kwargs.get('service')

        repo = self.accessors.get_repo_details(
            user=self.request.user,
            repo_name=repo_name,
            repo_owner_username=org_name,
            repo_owner_service=service
        )

        if repo is None:
            repo = self.accessors.fetch_from_git_and_create_repo(
                user=self.request.user,
                repo_name=repo_name,
                repo_owner_username=org_name,
                repo_owner_service=service
            )

        self.check_object_permissions(self.request, repo)
        return repo

    def perform_update(self, serializer):
        # Check repo limits for users with legacy plans
        owner = self.owner
        if serializer.validated_data.get('active'):
            if owner.has_legacy_plan and owner.repo_credits <= 0:
                raise PermissionDenied("Private repository limit reached.")
        return super().perform_update(serializer)

    def destroy(self, request, *args, **kwargs):
        SegmentService().account_deleted_repository(self.request.user.ownerid, self.get_object())
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, url_path='statistics')
    def statistics(self, request, *args, **kwargs):
        # Only get viewable repositories
        queryset = self.owner.repository_set.viewable_repos(
            self.request.user
        )

        # Filter the repositories by the list of repositories if it is set
        if self.request.query_params.get("names"):
            queryset = queryset.filter(name__in=self.request.query_params.get("names", []))

        # Then only get the repositories with totals and then annotate the latest commit
        results = queryset.exclude_uncovered(
        ).with_latest_commit_totals_before(
            self.request.query_params.get("before_date", datetime.now().isoformat()),
            self.request.query_params.get("branch", None),
            include_previous_totals=True
        ).get_aggregated_coverage()

        return Response(data={
            "repos_count": results["repo_count"],
            "sum_lines": results["sum_lines"],
            "sum_hits": results["sum_hits"],
            "sum_partials": results["sum_partials"],
            "sum_misses": results["sum_misses"],
            "weighted_coverage": results["weighted_coverage"],
            "weighted_coverage_change": results["weighted_coverage_change"],
            "average_complexity": results["average_complexity"],
        })

    @action(detail=True, methods=['patch'], url_path='regenerate-upload-token')
    def regenerate_upload_token(self, request, *args, **kwargs):
        repo = self.get_object()
        repo.upload_token = uuid.uuid4()
        repo.save()
        return Response(self.get_serializer(repo).data)

    @action(detail=True, methods=['patch'])
    def erase(self, request, *args, **kwargs):
        self._assert_is_admin()
        repo = self.get_object()
        repo.flush()
        SegmentService.account_erased_repository(self.request.user.ownerid, repo)
        return Response(self.get_serializer(repo).data)

    @action(detail=True, methods=['post'])
    def encode(self, request, *args, **kwargs):
        serializer = SecretStringPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner, repo = self.owner, self.get_object()

        to_encode = '/'.join((
            owner.service,
            owner.service_id,
            repo.service_id,
            serializer.validated_data['value']
        ))

        return Response(
            SecretStringPayloadSerializer(
                {"value": encode_secret_string(to_encode)}
            ).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['put'], url_path='reset-webhook')
    @torngit_safe
    def reset_webhook(self, request, *args, **kwargs):
        repo = self.get_object()
        repository_service = RepoProviderService().get_adapter(self.request.user, repo)

        if repo.hookid:
            delete_webhook_on_provider(repository_service, repo)
            repo.hookid = None
            repo.save()

        repo.hookid = create_webhook_on_provider(repository_service, repo)
        repo.save()

        return Response(
            self.get_serializer(repo).data,
            status=status.HTTP_200_OK
        )
