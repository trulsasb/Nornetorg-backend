import secrets

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.order import CartOrder, CartOrderStatus
from utils.env import settings

router = APIRouter(prefix="/checkout", tags=["Stripe Payment"])


@router.post("/{cart_order_id}/stripe/initiate")
def initiate_stripe_payment(cart_order_id: int, db: Session = Depends(get_db)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe er ikke konfigurert")
    stripe.api_key = settings.STRIPE_SECRET_KEY

    cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first()
    if not cart_order:
        raise HTTPException(status_code=404, detail="Ordre ikke funnet")
    if cart_order.payment_provider != "stripe":
        raise HTTPException(status_code=400, detail="Denne ordren skal betales med Vipps, ikke Stripe")
    if cart_order.status != CartOrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=409, detail="Ordren venter ikke lenger på betaling")

    status_token = secrets.token_urlsafe(24)
    cart_order.status_token = status_token

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "nok",
                        "product_data": {"name": f"NorneTorg-ordre #{cart_order.id}"},
                        "unit_amount": int(round(cart_order.total_amount * 100)),
                    },
                    "quantity": 1,
                }
            ],
            # transfer_group lets the webhook's later Transfer.create calls
            # (Modul 7) be reconciled back to this specific payment in the
            # Stripe dashboard -- the split itself still happens via
            # separate Transfer objects, not natively in this Session.
            # metadata is set on BOTH the Session and the underlying
            # PaymentIntent -- checkout.session.expired delivers a Session
            # object, but payment_intent.payment_failed delivers a
            # PaymentIntent, which does NOT inherit the Session's metadata
            # unless set here explicitly too.
            payment_intent_data={
                "transfer_group": f"cart_order_{cart_order.id}",
                "metadata": {"cart_order_id": str(cart_order.id)},
            },
            success_url=f"{settings.FRONTEND_URL}/checkout/success?cart_order_id={cart_order.id}",
            cancel_url=f"{settings.FRONTEND_URL}/checkout/cancel?cart_order_id={cart_order.id}",
            metadata={"cart_order_id": str(cart_order.id)},
        )
    except stripe.error.StripeError as e:
        db.commit()  # keep the status_token even if Stripe itself failed, harmless
        raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")

    cart_order.stripe_payment_intent_id = session.id
    db.commit()

    return {"cart_order_id": cart_order.id, "checkout_url": session.url, "status_token": status_token}


@router.get("/{cart_order_id}/status")
def get_cart_order_status(cart_order_id: int, token: str | None = None, db: Session = Depends(get_db)):
    cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first()
    if not cart_order:
        raise HTTPException(status_code=404, detail="Ordre ikke funnet")

    # Same pattern as Vitalityboost's payment-status fix: required and
    # checked for any order that actually has a token (i.e. any order whose
    # payment has been initiated). No token yet issued -> nothing to leak.
    if cart_order.status_token and (token is None or not secrets.compare_digest(token, cart_order.status_token)):
        raise HTTPException(status_code=404, detail="Ordre ikke funnet")

    return {
        "cart_order_id": cart_order.id,
        "status": cart_order.status.value,
        "seller_suborders": [
            {"seller_id": s.seller_id, "status": s.status.value, "subtotal_amount": s.subtotal_amount}
            for s in cart_order.seller_suborders
        ],
    }
