import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.seller import Seller
from models.user import User
from routers.auth import get_current_seller_user, require_seller_permission
from services.vipps_auth import VippsAuth, VippsAuthError
from utils.crypto import encrypt_value
from utils.env import settings

router = APIRouter(prefix="/sellers/payments", tags=["Seller Payments"])

_can_manage_payments = [Depends(require_seller_permission("can_manage_payment_methods"))]


def _get_own_seller(current_user: User, db: Session) -> Seller:
    # current_user.seller_id is the tenant boundary -- never accept a
    # seller id from the request itself. See SPEC.md 4.2.
    seller = db.query(Seller).filter(Seller.id == current_user.seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Selger ikke funnet")
    return seller


# ---------------------------------------------------------
# STRIPE CONNECT (Express) -- for RECEIVING split payments
# ---------------------------------------------------------


@router.post("/stripe/connect", dependencies=_can_manage_payments)
def connect_stripe(
    current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe er ikke konfigurert på plattformen")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    seller = _get_own_seller(current_user, db)

    if not seller.stripe_account_id:
        try:
            account = stripe.Account.create(
                type="express",
                country="NO",
                email=current_user.email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")
        seller.stripe_account_id = account.id
        db.commit()

    try:
        account_link = stripe.AccountLink.create(
            account=seller.stripe_account_id,
            refresh_url=f"{settings.FRONTEND_URL}/selger/betalinger/stripe/refresh",
            return_url=f"{settings.FRONTEND_URL}/selger/betalinger/stripe/ferdig",
            type="account_onboarding",
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")

    return {"onboarding_url": account_link.url}


@router.get("/stripe/status")
def stripe_status(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    seller = _get_own_seller(current_user, db)
    return {
        "connected": bool(seller.stripe_account_id),
        "onboarding_complete": seller.stripe_onboarding_complete,
    }


# ---------------------------------------------------------
# VIPPS -- for RECEIVING Vipps payments directly (single-seller carts,
# see SPEC.md 3.1/4.1)
# ---------------------------------------------------------


class ConnectVippsRequest(BaseModel):
    client_id: str
    client_secret: str
    subscription_key: str
    msn: str
    # Returned by Vipps when the seller registers a webhook via their own
    # POST /webhooks call -- see Modul 8 (vipps_webhook.py) for why this is
    # per-seller rather than a shared platform secret.
    webhook_secret: str


@router.post("/vipps/connect", dependencies=_can_manage_payments)
def connect_vipps(
    payload: ConnectVippsRequest,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    seller = _get_own_seller(current_user, db)

    # Verify against Vipps itself before storing anything -- don't mark a
    # seller "connected" just because they typed something key-shaped.
    auth = VippsAuth(payload.client_id, payload.client_secret, payload.subscription_key, settings.VIPPS_BASE_URL)
    try:
        auth.fetch_access_token()
    except VippsAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))

    seller.vipps_client_id_encrypted = encrypt_value(payload.client_id)
    seller.vipps_client_secret_encrypted = encrypt_value(payload.client_secret)
    seller.vipps_subscription_key_encrypted = encrypt_value(payload.subscription_key)
    seller.vipps_msn_encrypted = encrypt_value(payload.msn)
    seller.vipps_webhook_secret_encrypted = encrypt_value(payload.webhook_secret)
    seller.vipps_onboarding_complete = True
    # Deliberately NOT touching vipps_suspended_for_unpaid_commission here --
    # that flag is only cleared by actually settling owed commission
    # (Modul 10), never by reconnecting credentials. Otherwise a seller
    # could evade the dunning suspension just by disconnecting/reconnecting.
    db.commit()

    return {"connected": True}


@router.get("/vipps/status")
def vipps_status(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    seller = _get_own_seller(current_user, db)
    return {
        "connected": seller.vipps_onboarding_complete,
        "suspended_for_unpaid_commission": seller.vipps_suspended_for_unpaid_commission,
    }


@router.delete("/vipps/connect", dependencies=_can_manage_payments)
def disconnect_vipps(
    current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    seller = _get_own_seller(current_user, db)
    seller.vipps_client_id_encrypted = None
    seller.vipps_client_secret_encrypted = None
    seller.vipps_subscription_key_encrypted = None
    seller.vipps_msn_encrypted = None
    seller.vipps_webhook_secret_encrypted = None
    seller.vipps_onboarding_complete = False
    db.commit()
    return {"connected": False}


# ---------------------------------------------------------
# PROVISJONS-BETALINGSMETODE -- plattformens EGEN Stripe-konto trekker
# provisjon fra selgeren. Adskilt fra Stripe Connect over. Se SPEC.md 3.1/3.4.
# ---------------------------------------------------------


@router.post("/commission-method/setup-intent", dependencies=_can_manage_payments)
def create_commission_setup_intent(
    current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe er ikke konfigurert på plattformen")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    seller = _get_own_seller(current_user, db)

    if not seller.commission_stripe_customer_id:
        try:
            customer = stripe.Customer.create(email=current_user.email, name=seller.store_name)
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")
        seller.commission_stripe_customer_id = customer.id
        db.commit()

    try:
        setup_intent = stripe.SetupIntent.create(
            customer=seller.commission_stripe_customer_id,
            payment_method_types=["card"],
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")

    return {"client_secret": setup_intent.client_secret}


class ConfirmCommissionMethodRequest(BaseModel):
    payment_method_id: str


@router.post("/commission-method/confirm", dependencies=_can_manage_payments)
def confirm_commission_method(
    payload: ConfirmCommissionMethodRequest,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe er ikke konfigurert på plattformen")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    seller = _get_own_seller(current_user, db)

    if not seller.commission_stripe_customer_id:
        raise HTTPException(status_code=400, detail="Ingen provisjons-kunde opprettet ennå")

    try:
        payment_method = stripe.PaymentMethod.retrieve(payload.payment_method_id)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe-feil: {e}")

    # A seller could in principle submit an arbitrary payment_method_id --
    # only accept one actually attached to THIS seller's own customer object.
    if payment_method.customer != seller.commission_stripe_customer_id:
        raise HTTPException(status_code=400, detail="Betalingsmetoden tilhører ikke denne selgeren")

    seller.commission_payment_method_id = payload.payment_method_id
    db.commit()

    return {"connected": True}


@router.get("/commission-method/status")
def commission_method_status(
    current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    seller = _get_own_seller(current_user, db)
    return {"connected": bool(seller.commission_payment_method_id)}
