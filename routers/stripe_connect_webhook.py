import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.seller import Seller
from utils.env import settings

router = APIRouter(prefix="/webhooks/stripe-connect", tags=["Webhooks"])


@router.post("/")
async def stripe_connect_webhook(request: Request, db: Session = Depends(get_db)):
    """Confirms a seller's Stripe Express onboarding actually completed --
    redirecting them back from the AccountLink return_url does NOT guarantee
    they finished (they could abandon partway and still land on return_url
    in some flows). Only trust Stripe's own account.updated event."""

    if not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe Connect webhook secret not configured")

    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(raw_body, signature, settings.STRIPE_CONNECT_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event["type"] == "account.updated":
        account = event["data"]["object"]
        seller = db.query(Seller).filter(Seller.stripe_account_id == account["id"]).first()
        if seller:
            seller.stripe_onboarding_complete = bool(
                account.get("details_submitted") and account.get("charges_enabled")
            )
            db.commit()

    return {"status": "ok"}
