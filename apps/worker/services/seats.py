import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from database.models import Owner
from services.activation import activate_user, schedule_new_user_activated_task
from services.decoration import _is_bot_account
from services.repository import EnrichedPull
from shared.plan.service import PlanService

log = logging.getLogger(__name__)


class ShouldActivateSeat(Enum):
    NO_ACTIVATE = "no_activate"
    MANUAL_ACTIVATE = "manual_activate"
    AUTO_ACTIVATE = "auto_activate"


@dataclass
class SeatActivationInfo:
    should_activate_seat: ShouldActivateSeat = ShouldActivateSeat.NO_ACTIVATE
    owner_id: int | None = None
    author_id: int | None = None
    reason: str | None = None


def determine_seat_activation(pull: EnrichedPull) -> SeatActivationInfo:
    """
    this function will determine if a user needs to be activated based on information about the user, their org, their repo, and the PR
    1. if the repo is public they don't need to be activated
    2. get repostiory owner info
    2.1 (custom gitlab logic) if they are on gitlab we get their root group as the org instead of the repo owner
    3. get pr author info
    4. if org doesn't use seats, or author is included in seats already then no need to be activated
    5. if author is bot user then no need to be activated
    6. user must either be manually activated or auto activated
    """
    db_pull = pull.database_pull
    provider_pull = pull.provider_pull
    if provider_pull is None:
        log.warning(
            "Provider pull was None when determining whether to activate seat for user",
            extra={
                "pullid": db_pull.pullid,
                "repoid": db_pull.repoid,
                "head_commit": db_pull.head,
                "base_commit": db_pull.base,
            },
        )
        return SeatActivationInfo(reason="no_provider_pull")

    if db_pull.repository.private is False:
        return SeatActivationInfo(reason="public_repo")

    org = db_pull.repository.owner

    db_session: Session = db_pull.get_db_session()

    # do not access plan directly - only through PlanService
    org_plan = PlanService(current_org=org)
    # use the org that has the plan - for GL this is the root_org rather than the repository.owner org
    org = org_plan.current_org

    if not org_plan.is_pr_billing_plan:
        return SeatActivationInfo(reason="no_pr_billing_plan")

    pr_author = (
        db_session.query(Owner)
        .filter(
            Owner.service == org.service,
            Owner.service_id == provider_pull.get("author", {}).get("id"),
        )
        .first()
    )

    if not pr_author:
        log.info(
            "PR author not found in database",
            extra={
                "author_service": org.service,
                "author_service_id": provider_pull.get("author", {}).get("id"),
                "author_username": provider_pull.get("author", {}).get("username"),
            },
        )
        return SeatActivationInfo(reason="no_pr_author")

    if (
        org.plan_activated_users is not None
        and pr_author.ownerid in org.plan_activated_users
    ):
        return SeatActivationInfo(reason="author_in_plan_activated_users")

    if _is_bot_account(pr_author):
        return SeatActivationInfo(reason="is_bot_account")

    if not org.plan_auto_activate:
        return SeatActivationInfo(
            ShouldActivateSeat.MANUAL_ACTIVATE,
            org.ownerid,
            pr_author.ownerid,
            reason="manual_activate",
        )
    else:
        return SeatActivationInfo(
            ShouldActivateSeat.AUTO_ACTIVATE,
            org.ownerid,
            pr_author.ownerid,
            reason="auto_activate",
        )


def check_seat_activation(db_session: Session, pull: EnrichedPull) -> bool:
    activate_seat_info = determine_seat_activation(pull)

    match activate_seat_info.should_activate_seat:
        case ShouldActivateSeat.AUTO_ACTIVATE:
            assert activate_seat_info.owner_id
            assert activate_seat_info.author_id
            successful_activation = activate_user(
                db_session=db_session,
                org_ownerid=activate_seat_info.owner_id,
                user_ownerid=activate_seat_info.author_id,
            )
            if successful_activation:
                schedule_new_user_activated_task(
                    activate_seat_info.owner_id,
                    activate_seat_info.author_id,
                )
                should_show_upgrade_message = False
            else:
                should_show_upgrade_message = True
        case ShouldActivateSeat.MANUAL_ACTIVATE:
            should_show_upgrade_message = True
        case ShouldActivateSeat.NO_ACTIVATE:
            should_show_upgrade_message = False

    return should_show_upgrade_message
