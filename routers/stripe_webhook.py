import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.order import CartOrder, CartOrderStatus
from services.order_service import release_failed_cart_order
from tasks.transfers import create_seller_transfers
from utils.env import settings

router = APIRouter(prefix="/webhooks/stripe", tags=["Webhooks"])


@router.post("/")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook secret not configured")

    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(raw_body, signature, settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        cart_order_id = obj.get("metadata", {}).get("cart_order_id")
        cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first() if cart_order_id else None
        # Guarded on PENDING_PAYMENT so a duplicate webhook delivery can't
        # re-trigger transfers or double-mark an already-settled order.
        if cart_order and cart_order.status == CartOrderStatus.PENDING_PAYMENT:
            cart_order.status = CartOrderStatus.PAID
            db.commit()
            create_seller_transfers.delay(cart_order.id)

    elif event_type in ("checkout.session.expired", "payment_intent.payment_failed"):
        cart_order_id = obj.get("metadata", {}).get("cart_order_id")
        if cart_order_id:
            release_failed_cart_order(db, int(cart_order_id))
            db.commit()

    return {"status": "ok"}
