import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.commission import CommissionLedger
from models.order import SellerSubOrderStatus
from models.payment import Payment, PaymentEvent
from services.order_service import recompute_cart_order_status, release_failed_seller_suborder
from utils.crypto import decrypt_value
from utils.env import settings

router = APIRouter(prefix="/webhooks/vipps", tags=["Webhooks"])

_SUCCESS_EVENTS = {"AUTHORIZED", "CAPTURED"}
_FAILURE_EVENTS = {"CANCELLED", "EXPIRED", "TERMINATED", "FAILED"}
_EXPECTED_SIGNED_HEADERS = "x-ms-date;host;x-ms-content-sha256"


def _verify_signature(request: Request, raw_body: bytes, webhook_secret: str) -> None:
    """Verifies Vipps' HMAC-SHA256 webhook signature -- same scheme (and
    same implementation) as Vitalityboost's stripe/vipps webhook, proven
    correct there: https://developer.vippsmobilepay.com/docs/APIs/webhooks-api/request-authentication/"""
    date_header = request.headers.get("x-ms-date")
    content_hash_header = request.headers.get("x-ms-content-sha256")
    authorization = request.headers.get("authorization")
    host = request.headers.get("host")

    if not all([date_header, content_hash_header, authorization, host]):
        raise HTTPException(status_code=401, detail="Missing webhook authentication headers")

    expected_content_hash = base64.b64encode(hashlib.sha256(raw_body).digest()).decode()
    if not hmac.compare_digest(expected_content_hash, content_hash_header):
        raise HTTPException(status_code=401, detail="Webhook content hash mismatch")

    try:
        scheme, rest = authorization.split(" ", 1)
        params = dict(p.split("=", 1) for p in rest.split("&"))
        signed_headers = params["SignedHeaders"]
        signature = params["Signature"]
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed Authorization header")

    if scheme != "HMAC-SHA256" or signed_headers != _EXPECTED_SIGNED_HEADERS:
        raise HTTPException(status_code=401, detail="Unexpected Authorization header format")

    path_and_query = request.url.path
    if request.url.query:
        path_and_query += f"?{request.url.query}"

    string_to_sign = f"POST\n{path_and_query}\n{date_header};{host};{content_hash_header}"
    expected_signature = base64.b64encode(
        hmac.new(webhook_secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/")
async def vipps_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    payload = json.loads(raw_body)

    reference = payload.get("reference")
    event_name = payload.get("name") or payload.get("eventName") or "unknown"

    if not reference:
        return {"status": "ignored", "reason": "no reference in payload"}

    payment = db.query(Payment).filter(Payment.external_reference == reference, Payment.provider == "vipps").first()
    if not payment:
        return {"status": "ignored", "reason": "unknown reference"}

    suborder = payment.seller_suborder
    seller = suborder.seller

    # Each seller's OWN Vipps webhook secret verifies this event -- not a
    # platform-wide secret, since each seller has their own Vipps agreement
    # (Modul 3). Decrypted only for this single verification, never returned.
    if not seller.vipps_webhook_secret_encrypted:
        raise HTTPException(status_code=503, detail="Vipps webhook secret not configured for this seller")
    _verify_signature(request, raw_body, decrypt_value(seller.vipps_webhook_secret_encrypted))

    # Idempotency: a duplicate webhook delivery for an already-settled
    # payment must not re-run side effects (double commission booking,
    # re-releasing already-restored stock).
    if payment.status != "pending":
        return {"status": "ok"}

    db.add(PaymentEvent(payment_id=payment.id, event_type=f"vipps_{event_name}", data=str(payload)))

    if event_name in _SUCCESS_EVENTS:
        payment.status = "completed"
        suborder.status = SellerSubOrderStatus.PAID
        recompute_cart_order_status(suborder.cart_order)

        # Commission wasn't collected at transaction time (money went
        # straight to the seller) -- book it as owed, settled later by
        # Modul 10's periodic draw. See SPEC.md 3.1.
        db.add(
            CommissionLedger(
                seller_suborder_id=suborder.id,
                seller_id=suborder.seller_id,
                amount=round(suborder.subtotal_amount * settings.PLATFORM_COMMISSION_RATE, 2),
            )
        )

    elif event_name in _FAILURE_EVENTS:
        payment.status = "failed"
        release_failed_seller_suborder(db, suborder.id)

    db.commit()
    return {"status": "ok"}
