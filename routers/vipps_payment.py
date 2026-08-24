import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.order import CartOrder, CartOrderStatus, SellerSubOrder, SellerSubOrderStatus
from models.payment import Payment
from services.vipps_auth import VippsAuth, VippsAuthError
from utils.crypto import decrypt_value
from utils.env import settings

router = APIRouter(prefix="/checkout", tags=["Vipps Payment"])


@router.post("/{cart_order_id}/vipps/initiate/{seller_id}")
def initiate_vipps_payment(cart_order_id: int, seller_id: int, db: Session = Depends(get_db)):
    cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first()
    if not cart_order:
        raise HTTPException(status_code=404, detail="Ordre ikke funnet")
    if cart_order.payment_provider != "vipps":
        raise HTTPException(status_code=400, detail="Denne ordren skal betales med Stripe, ikke Vipps")

    suborder = (
        db.query(SellerSubOrder)
        .filter(SellerSubOrder.cart_order_id == cart_order_id, SellerSubOrder.seller_id == seller_id)
        .first()
    )
    if not suborder:
        raise HTTPException(status_code=404, detail="Denne selgeren er ikke del av denne ordren")
    if suborder.status != SellerSubOrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=409, detail="Denne delbetalingen venter ikke lenger på betaling")

    seller = suborder.seller
    if not seller.vipps_onboarding_complete:
        raise HTTPException(status_code=400, detail=f"{seller.store_name} har ikke koblet til Vipps")

    auth = VippsAuth(
        client_id=decrypt_value(seller.vipps_client_id_encrypted),
        client_secret=decrypt_value(seller.vipps_client_secret_encrypted),
        subscription_key=decrypt_value(seller.vipps_subscription_key_encrypted),
        base_url=settings.VIPPS_BASE_URL,
    )
    msn = decrypt_value(seller.vipps_msn_encrypted)
    reference = f"nornetorg-{cart_order.id}-{suborder.id}"

    try:
        headers = auth.get_headers()
        headers["Merchant-Serial-Number"] = msn
        body = {
            "amount": {"currency": "NOK", "value": int(round(suborder.subtotal_amount * 100))},
            "paymentMethod": {"type": "WALLET"},
            "reference": reference,
            "returnUrl": f"{settings.FRONTEND_URL}/checkout/complete?cart_order_id={cart_order.id}&seller_id={seller_id}",
            "userFlow": "WEB_REDIRECT",
            "paymentDescription": f"NorneTorg-ordre #{cart_order.id} hos {seller.store_name}",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"{settings.VIPPS_BASE_URL}/epayment/v1/payments", headers=headers, json=body)
        if resp.status_code >= 400:
            raise VippsAuthError(resp.text)
        data = resp.json()
    except VippsAuthError as e:
        raise HTTPException(status_code=502, detail=f"Vipps-feil: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Kunne ikke nå Vipps: {e}")

    db.add(
        Payment(
            seller_suborder_id=suborder.id,
            provider="vipps",
            status="pending",
            amount=suborder.subtotal_amount,
            currency="NOK",
            external_reference=reference,
        )
    )

    # Reused across every seller's initiate call for this cart -- see the
    # matching fix in stripe_payment.py. Vipps in particular issues this
    # token once and needs it to keep working across N separate calls.
    status_token = cart_order.status_token or secrets.token_urlsafe(24)
    cart_order.status_token = status_token
    db.commit()

    return {
        "cart_order_id": cart_order.id,
        "seller_id": seller_id,
        "checkout_url": data.get("redirectUrl"),
        "status_token": status_token,
    }
