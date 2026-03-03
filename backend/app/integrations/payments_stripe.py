from __future__ import annotations

from typing import Any, Dict, Optional

import stripe


class StripeError(Exception):
    pass


def is_stripe_configured(secret_key: str | None) -> bool:
    if not secret_key:
        return False

    normalized = secret_key.strip()
    if not normalized:
        return False

    placeholder_values = {
        "sk_test",
        "sk_live",
        "sk_test_xxx",
        "sk_live_xxx",
        "change-me",
        "changeme",
    }
    if normalized in placeholder_values:
        return False

    if normalized.endswith("_xxx"):
        return False

    return normalized.startswith("sk_test_") or normalized.startswith("sk_live_")


def init_stripe(secret_key: str) -> None:
    if not is_stripe_configured(secret_key):
        raise StripeError("Stripe secret key is not configured")
    stripe.api_key = secret_key


def create_checkout_session(
    *,
    secret_key: str,
    order_id: str,
    product_id: str,
    product_name: str,
    unit_amount_cents: int,
    currency: str,
    stripe_price_id: Optional[str],
    frontend_url: str,
    customer_email: Optional[str] = None,
    success_url_override: Optional[str] = None,
    cancel_url_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates Stripe Checkout Session.
    We always attach metadata.order_id so webhook can link payment to our Order.
    """
    init_stripe(secret_key)

    default_success_url = f"{frontend_url}/pay/success?order_id={order_id}&session_id={{CHECKOUT_SESSION_ID}}"
    default_cancel_url = f"{frontend_url}/pay/cancel"

    success_url = (success_url_override or "").strip() or default_success_url
    cancel_url = (cancel_url_override or "").strip() or default_cancel_url

    line_item: Dict[str, Any]
    if stripe_price_id:
        line_item = {"price": stripe_price_id, "quantity": 1}
    else:
        line_item = {
            "price_data": {
                "currency": currency.lower(),
                "unit_amount": int(unit_amount_cents),
                "product_data": {
                    "name": product_name,
                    "metadata": {"product_id": product_id},
                },
            },
            "quantity": 1,
        }

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[line_item],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email,
            metadata={
                "order_id": order_id,
                "product_id": product_id,
            },
        )
    except Exception as e:
        raise StripeError(f"Failed to create checkout session: {e}") from e

    return {"id": session["id"], "url": session.get("url")}


def retrieve_checkout_session(*, secret_key: str, session_id: str) -> Dict[str, Any]:
    init_stripe(secret_key)
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise StripeError(f"Failed to retrieve checkout session: {e}") from e
    return session.to_dict()


def construct_event(
    *,
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
) -> Dict[str, Any]:
    """
    Verifies Stripe webhook signature and returns event as dict.
    """
    if not webhook_secret or not webhook_secret.startswith("whsec_"):
        raise StripeError("Stripe webhook secret is not configured")
    if not signature_header:
        raise StripeError("Missing Stripe-Signature header")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=signature_header, secret=webhook_secret)
    except stripe.error.SignatureVerificationError as e:
        raise StripeError("Invalid webhook signature") from e
    except Exception as e:
        raise StripeError(f"Webhook parse error: {e}") from e
    return event.to_dict()