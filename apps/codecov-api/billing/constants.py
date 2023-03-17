class StripeHTTPHeaders:
    """
    Header-strings associated with Stripe webhook events.
    """

    # https://stripe.com/docs/webhooks/signatures#verify-official-libraries
    SIGNATURE = "HTTP_STRIPE_SIGNATURE"


class StripeWebhookEvents:
    subscribed_events = (
        "checkout.session.completed",
        "customer.created",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.updated",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
        "subscription_schedule.created",
        "subscription_schedule.released",
        "subscription_schedule.updated",
    )


FREE_PLAN_NAME = "users-free"  # marketing name: Free
GHM_PLAN_NAME = "users"
BASIC_PLAN_NAME = "users-basic"


NON_PR_AUTHOR_PAID_USER_PLAN_REPRESENTATIONS = {
    "users-inappm": {
        "marketing_name": "Pro Team",
        "value": "users-inappm",
        "billing_rate": "monthly",
        "base_unit_price": 12,
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
    "users-inappy": {
        "marketing_name": "Pro Team",
        "value": "users-inappy",
        "billing_rate": "annually",
        "base_unit_price": 10,
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
}


PR_AUTHOR_PAID_USER_PLAN_REPRESENTATIONS = {
    "users-pr-inappm": {
        "marketing_name": "Pro Team",
        "value": "users-pr-inappm",
        "billing_rate": "monthly",
        "base_unit_price": 12,
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
    "users-pr-inappy": {
        "marketing_name": "Pro Team",
        "value": "users-pr-inappy",
        "billing_rate": "annually",
        "base_unit_price": 10,
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
}

SENTRY_PAID_USER_PLAN_REPRESENTATIONS = {
    "users-sentrym": {
        "marketing_name": "Sentry Pro Team",
        "value": "users-sentrym",
        "billing_rate": "monthly",
        "base_unit_price": 12,
        "benefits": [
            "Includes 5 seats",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
        "trial_days": 14,
    },
    "users-sentryy": {
        "marketing_name": "Sentry Pro Team",
        "value": "users-sentryy",
        "billing_rate": "annually",
        "base_unit_price": 10,
        "benefits": [
            "Includes 5 seats",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
        "trial_days": 14,
    },
}

# TODO: Update these values
ENTERPRISE_CLOUD_USER_PLAN_REPRESENTATIONS = {
    "users-enterprisem": {
        "marketing_name": "Enterprise Cloud",
        "value": "users-enterprisem",
        "billing_rate": "monthly",
        "base_unit_price": 12,  # Update me
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
    "users-enterprisey": {
        "marketing_name": "Enterprise Cloud",
        "value": "users-enterprisey",
        "billing_rate": "annually",
        "base_unit_price": 10,  # Update me
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
            "Priority Support",
        ],
    },
}

GHM_PLAN_REPRESENTATION = {
    GHM_PLAN_NAME: {
        "marketing_name": "Github Marketplace",
        "value": GHM_PLAN_NAME,
        "billing_rate": None,
        "base_unit_price": 12,
        "benefits": [
            "Configurable # of users",
            "Unlimited public repositories",
            "Unlimited private repositories",
        ],
    }
}

FREE_PLAN_REPRESENTATIONS = {
    FREE_PLAN_NAME: {
        "marketing_name": "Free",
        "value": FREE_PLAN_NAME,
        "billing_rate": None,
        "base_unit_price": 0,
        "benefits": [
            "Up to 1 user",
            "Unlimited public repositories",
            "Unlimited private repositories",
        ],
    },
    BASIC_PLAN_NAME: {
        "marketing_name": "Basic",
        "value": BASIC_PLAN_NAME,
        "billing_rate": None,
        "base_unit_price": 0,
        "monthly_uploads_limit": 250,
        "benefits": [
            "Up to 1 user",
            "Unlimited public repositories",
            "Unlimited private repositories",
        ],
    },
}

USER_PLAN_REPRESENTATIONS = {
    **FREE_PLAN_REPRESENTATIONS,
    **NON_PR_AUTHOR_PAID_USER_PLAN_REPRESENTATIONS,
    **PR_AUTHOR_PAID_USER_PLAN_REPRESENTATIONS,
    **SENTRY_PAID_USER_PLAN_REPRESENTATIONS,
    **GHM_PLAN_REPRESENTATION,
    **ENTERPRISE_CLOUD_USER_PLAN_REPRESENTATIONS,
}


REMOVED_INVOICE_STATUSES = ["draft", "void"]
