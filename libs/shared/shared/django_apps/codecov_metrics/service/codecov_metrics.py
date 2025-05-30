import logging
from typing import Any

from ..models import UserOnboardingLifeCycleMetrics

log = logging.getLogger(__name__)


class UserOnboardingMetricsService:
    ALLOWED_EVENTS = {
        "VISITED_PAGE",
        "CLICKED_BUTTON",
        "COPIED_TEXT",
        "COMPLETED_UPLOAD",
        "INSTALLED_APP",
    }

    @staticmethod
    def create_user_onboarding_metric(org_id: int, event: str, payload: dict[str, Any]):
        if event not in UserOnboardingMetricsService.ALLOWED_EVENTS:
            log.warning("Incompatible event type", extra={"event_name": event})
            return

        metric, created = UserOnboardingLifeCycleMetrics.objects.get_or_create(
            org_id=org_id,
            event=event,
            additional_data=payload,
        )
        if created:
            return metric
        return None
