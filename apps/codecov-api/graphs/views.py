import logging

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from rest_framework import exceptions
from rest_framework.exceptions import NotFound
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

import shared.reports.api_report_service as report_service
from api.shared.mixins import RepoPropertyMixin
from core.models import Branch, Pull
from graphs.settings import settings
from services.bundle_analysis import load_report
from services.components import commit_components
from shared.django_apps.core.models import Commit
from shared.metrics import Counter, inc_counter

from .helpers.badge import (
    format_bundle_bytes,
    format_coverage_precision,
    get_badge,
    get_bundle_badge,
)
from .helpers.graphs import icicle, sunburst, tree
from .mixins import GraphBadgeAPIMixin

log = logging.getLogger(__name__)

FLARE_USE_COUNTER = Counter(
    "graph_activity",
    "How are graphs and flare being used?",
    [
        "flare_request",
    ],
)
FLARE_SUCCESS_COUNTER = Counter(
    "graph_success",
    "How often are graphs successfully generated?",
    [
        "graph_type",
    ],
)


class IgnoreClientContentNegotiation(DefaultContentNegotiation):
    def select_parser(self, request, parsers):
        """
        Select the first parser in the `.parser_classes` list.
        """
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix):
        """
        Select the first renderer in the `.renderer_classes` list.
        """
        try:
            return super().select_renderer(request, renderers, format_suffix)
        except exceptions.NotAcceptable:
            log.info(
                f"Recieved unsupported HTTP_ACCEPT header: {request.META.get('HTTP_ACCEPT')}"
            )
            return (renderers[0], renderers[0].media_type)


class BadgeHandler(APIView, RepoPropertyMixin, GraphBadgeAPIMixin):
    content_negotiation_class = IgnoreClientContentNegotiation

    permission_classes = [AllowAny]

    extensions = ["svg", "txt"]
    precisions = ["0", "1", "2"]
    filename = "badge"

    def get_object(self, request, *args, **kwargs):
        # Validate coverage precision
        precision = self.request.query_params.get("precision", "0")
        if precision not in self.precisions:
            raise NotFound("Coverage precision should be one of [ 0 || 1 || 2 ]")

        coverage, coverage_range = self.get_coverage()

        # Format coverage according to precision
        coverage = format_coverage_precision(coverage, precision)

        if self.kwargs.get("ext") == "txt":
            return coverage

        return get_badge(coverage, coverage_range, precision)

    def get_coverage(self):
        """
        Note: This endpoint has the behavior of returning a gray badge with the word 'unknown' instead of returning a 404
              when the user enters an invalid service, owner, repo or when coverage is not found for a branch.

              We also need to support service abbreviations for users already using them
        """
        coverage_range = [70, 100]

        try:
            repo = self.repo
        except Http404:
            log.warning("Repo not found", extra={"repo": self.kwargs.get("repo_name")})
            return None, coverage_range

        if repo.private and repo.image_token != self.request.query_params.get("token"):
            log.warning(
                "Token provided does not match repo's image token",
                extra={"repo": repo},
            )
            return None, coverage_range

        branch_name = self.kwargs.get("branch") or repo.branch
        branch = Branch.objects.filter(
            name=branch_name, repository_id=repo.repoid
        ).first()

        if branch is None:
            log.warning(
                "Branch not found", extra={"branch_name": branch_name, "repo": repo}
            )
            return None, coverage_range
        try:
            commit = repo.commits.filter(commitid=branch.head).first()
        except ObjectDoesNotExist:
            # if commit does not exist return None coverage
            log.warning("Commit not found", extra={"commit": branch.head})
            return None, coverage_range

        if repo.yaml and repo.yaml.get("coverage", {}).get("range") is not None:
            coverage_range = repo.yaml.get("coverage", {}).get("range")

        flag = self.request.query_params.get("flag")
        if flag:
            return self.flag_coverage(flag, commit), coverage_range

        component = self.request.query_params.get("component")
        if component:
            return self.component_coverage(component, commit), coverage_range

        coverage = (
            commit.totals.get("c")
            if commit is not None and commit.totals is not None
            else None
        )

        return coverage, coverage_range

    def flag_coverage(self, flag_name: str, commit: Commit):
        """
        Looks into a commit's report sessions and returns the coverage for a particular flag name.
        """
        if commit.full_report is None:
            log.warning(
                "Commit's report not found",
                extra={"commit": commit.commitid, "flag": flag_name},
            )
            return None
        flags = commit.full_report.flags
        if flags is None:
            return None
        flag = flags.get(flag_name)
        if flag:
            return flag.totals.coverage
        return None

    def component_coverage(self, component_identifier: str, commit: Commit):
        """
        Looks into a commit's report sessions and returns the coverage for a particular component.
        """
        report = commit.full_report
        if report is None:
            log.warning(
                "Commit's report not found",
                extra={"commit": commit.commitid, "component": component_identifier},
            )
            return None
        components = commit_components(commit, None)

        try:
            component = next(
                c
                for c in components
                if c.component_id == component_identifier
                or c.name == component_identifier
            )
        except StopIteration:
            # Component not found
            return None

        # Gets the flags present in commit's report and reduces to only those
        # that match at least one of the component's flag regexes.
        component_flags = component.get_matching_flags(report.get_flag_names())

        # Filters the commit report on the component's flags and paths.
        filtered_report = report.filter(flags=component_flags, paths=component.paths)

        return filtered_report.totals.coverage


class BundleBadgeHandler(APIView, RepoPropertyMixin, GraphBadgeAPIMixin):
    content_negotiation_class = IgnoreClientContentNegotiation

    permission_classes = [AllowAny]

    extensions = ["svg", "txt"]
    precisions = ["0", "1", "2"]
    filename = "bundle-badge"

    def get_object(self, request, *args, **kwargs):
        # Validate precision query param
        precision = self.request.query_params.get("precision", "2")
        precision = int(precision) if precision in self.precisions else 2

        bundle_size_bytes = self.get_bundle_size()

        if self.kwargs.get("ext") == "txt":
            return (
                "unknown"
                if bundle_size_bytes is None
                else format_bundle_bytes(bundle_size_bytes, precision)
            )

        return get_bundle_badge(bundle_size_bytes, precision)

    def get_bundle_size(self) -> int | None:
        try:
            repo = self.repo
        except Http404:
            log.warning("Repo not found", extra={"repo": self.kwargs.get("repo_name")})
            return None

        if repo.private and repo.image_token != self.request.query_params.get("token"):
            log.warning(
                "Token provided does not match repo's image token",
                extra={"repo": repo},
            )
            return None

        branch_name = self.kwargs.get("branch") or repo.branch
        branch = Branch.objects.filter(
            name=branch_name, repository_id=repo.repoid
        ).first()

        if branch is None:
            log.warning(
                "Branch not found", extra={"branch_name": branch_name, "repo": repo}
            )
            return None

        commit: Commit = repo.commits.filter(commitid=branch.head).first()
        if commit is None:
            log.warning("Commit not found", extra={"commit": branch.head})
            return None

        commit_bundles = load_report(commit)

        if commit_bundles is None:
            log.warning(
                "Bundle analysis report not found for commit",
                extra={"commit": branch.head},
            )
            return None

        bundle_name = str(self.kwargs.get("bundle"))
        bundle = commit_bundles.bundle_report(bundle_name)

        if bundle is None:
            log.warning(
                "Bundle with provided name not found for commit",
                extra={"commit": branch.head},
            )
            return None

        return bundle.total_size()


class GraphHandler(APIView, RepoPropertyMixin, GraphBadgeAPIMixin):
    permission_classes = [AllowAny]

    extensions = ["svg"]
    filename = "graph"

    def get_object(self, request, *args, **kwargs):
        options = {}
        graph = self.kwargs.get("graph")

        # a flare graph has been requested
        inc_counter(FLARE_USE_COUNTER, labels={"flare_request": "received"})
        log.info(
            msg="flare graph activity",
            extra={"position": "start", "graph_type": graph, "kwargs": self.kwargs},
        )

        flare = self.get_flare()
        # flare success, will generate and return graph
        inc_counter(
            FLARE_USE_COUNTER, labels={"flare_request": "completed_successfully"}
        )

        if graph == "tree":
            options["width"] = int(
                self.request.query_params.get(
                    "width", settings["sunburst"]["options"]["width"] or 100
                )
            )
            options["height"] = int(
                self.request.query_params.get(
                    "height", settings["sunburst"]["options"]["height"] or 100
                )
            )
            inc_counter(FLARE_SUCCESS_COUNTER, labels={"graph_type": graph})
            log.info(
                msg="flare graph activity",
                extra={
                    "position": "success",
                    "graph_type": graph,
                    "kwargs": self.kwargs,
                },
            )
            return tree(flare, None, None, **options)
        elif graph == "icicle":
            options["width"] = int(
                self.request.query_params.get(
                    "width", settings["icicle"]["options"]["width"] or 100
                )
            )
            options["height"] = int(
                self.request.query_params.get(
                    "height", settings["icicle"]["options"]["height"] or 100
                )
            )
            inc_counter(FLARE_SUCCESS_COUNTER, labels={"graph_type": graph})
            log.info(
                msg="flare graph activity",
                extra={
                    "position": "success",
                    "graph_type": graph,
                    "kwargs": self.kwargs,
                },
            )
            return icicle(flare, **options)
        elif graph == "sunburst":
            options["width"] = int(
                self.request.query_params.get(
                    "width", settings["sunburst"]["options"]["width"] or 100
                )
            )
            options["height"] = int(
                self.request.query_params.get(
                    "height", settings["sunburst"]["options"]["height"] or 100
                )
            )
            inc_counter(FLARE_SUCCESS_COUNTER, labels={"graph_type": graph})
            log.info(
                msg="flare graph activity",
                extra={
                    "position": "success",
                    "graph_type": graph,
                    "kwargs": self.kwargs,
                },
            )
            return sunburst(flare, **options)

    def get_flare(self):
        pullid = self.kwargs.get("pullid")

        if not pullid:
            # pullid not in kwargs, try to generate flare from commit
            return self.get_commit_flare()
        else:
            # pullid was included in the request
            pull_flare = self.get_pull_flare(pullid)
            if pull_flare is None:
                # failed to get or generate flare from pull OR commit - graph request failed
                raise NotFound(
                    "Not found. Note: private repositories require ?token arguments"
                )
            return pull_flare

    def get_commit_flare(self):
        commit = self.get_commit()

        if commit is None:
            # could not find a commit - graph request failed
            raise NotFound(
                "Not found. Note: private repositories require ?token arguments"
            )

        # will attempt to build a report from a commit
        inc_counter(
            FLARE_USE_COUNTER, labels={"flare_request": "generating_fresh_flare"}
        )
        report = report_service.build_report_from_commit(commit)

        if report is None:
            # report generation failed
            raise NotFound("Not found. Note: file for chunks not found in storage")

        # report successfully generated
        inc_counter(
            FLARE_USE_COUNTER,
            labels={"flare_request": "successfully_generated_fresh_flare"},
        )
        return report.flare(None, [70, 100])

    def get_pull_flare(self, pullid):
        try:
            repo = self.repo
        except Http404:
            return None
        pull = Pull.objects.filter(pullid=pullid, repository_id=repo.repoid).first()
        if pull is not None:
            # pull found
            if pull._flare or pull._flare_storage_path:
                # pull has flare
                storage_location = "db" if pull._flare else "archive"
                inc_counter(
                    FLARE_USE_COUNTER,
                    labels={"flare_request": f"using_flare_from_{storage_location}"},
                )
                return pull.flare

        # pull not found or pull does not have flare, try to generate flare
        return self.get_commit_flare()

    def get_commit(self):
        try:
            repo = self.repo
            # repo included in request
        except Http404:
            return None
        if repo.private and repo.image_token != self.request.query_params.get("token"):
            # failed auth
            return None

        commitid = self.kwargs.get("commit")
        if commitid:
            # commitid included on request
            commit = repo.commits.filter(commitid=commitid).first()
        else:
            branch_name = self.kwargs.get("branch") or repo.branch
            branch = Branch.objects.filter(
                name=branch_name, repository_id=repo.repoid
            ).first()
            if branch is None:
                # failed to get a commit
                return None

            # found a commit by finding a branch
            commit = repo.commits.filter(commitid=branch.head).first()

        return commit
