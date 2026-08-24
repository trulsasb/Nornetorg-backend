from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.order import SellerSubOrder, SellerSubOrderStatus
from models.shipping import ShippingLabel
from models.user import User
from routers.auth import get_current_seller_user, require_seller_permission
from services.bring_client import Address, BringClientError, get_bring_client
from services.shipping_service import aggregate_shipping_bracket
from utils.env import settings

router = APIRouter(prefix="/sellers/orders", tags=["Seller Shipping"])

_can_fulfill = [Depends(require_seller_permission("can_view_orders"))]


def _get_own_suborder(seller_suborder_id: int, current_user: User, db: Session) -> SellerSubOrder:
    suborder = (
        db.query(SellerSubOrder)
        .filter(SellerSubOrder.id == seller_suborder_id, SellerSubOrder.seller_id == current_user.seller_id)
        .first()
    )
    if not suborder:
        raise HTTPException(status_code=404, detail="Ordre ikke funnet")
    return suborder


def _label_public(label: ShippingLabel) -> dict:
    return {
        "tracking_number": label.tracking_number,
        "label_url": label.label_url,
        "postage_cost": label.postage_cost,
        "purchased_at": label.purchased_at,
    }


@router.get("/{seller_suborder_id}/shipping-label")
def get_shipping_label(
    seller_suborder_id: int, current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    suborder = _get_own_suborder(seller_suborder_id, current_user, db)
    if not suborder.shipping_label:
        raise HTTPException(status_code=404, detail="Ingen fraktetikett kjøpt for denne ordren ennå")
    return _label_public(suborder.shipping_label)


@router.post("/{seller_suborder_id}/shipping-label", status_code=201, dependencies=_can_fulfill)
def buy_shipping_label(
    seller_suborder_id: int, current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    suborder = _get_own_suborder(seller_suborder_id, current_user, db)

    if suborder.status != SellerSubOrderStatus.PAID:
        raise HTTPException(status_code=400, detail="Kan bare kjøpe fraktetikett for en betalt ordre")

    # Idempotent: a label already bought for this suborder is returned as-is
    # rather than buying (and charging) a second one.
    if suborder.shipping_label:
        return _label_public(suborder.shipping_label)

    seller = suborder.seller
    if not (seller.business_address and seller.business_zip and seller.business_city):
        raise HTTPException(
            status_code=400, detail="Selgeren må oppgi returadresse (PUT /sellers/profile) før fraktetikett kan kjøpes"
        )

    bracket = aggregate_shipping_bracket(db, suborder)
    if not bracket:
        raise HTTPException(
            status_code=400,
            detail="Beregnet vekt overstiger største tilgjengelige fraktkategori -- krever manuell håndtering",
        )
    if not bracket.bring_product_code:
        raise HTTPException(status_code=400, detail=f"Fraktkategori '{bracket.label}' mangler en Bring-produktkode")

    if not settings.BRING_API_KEY or not settings.BRING_CUSTOMER_NUMBER:
        raise HTTPException(status_code=503, detail="Bring er ikke konfigurert på plattformen")

    cart_order = suborder.cart_order
    sender = Address(
        name=seller.store_name,
        address_line=seller.business_address,
        postal_code=seller.business_zip,
        city=seller.business_city,
    )
    recipient = Address(
        name=cart_order.customer_name or cart_order.customer_email,
        address_line=cart_order.shipping_address,
        postal_code=cart_order.shipping_zip,
        city=cart_order.shipping_city,
    )

    total_weight_g = sum(item.product.shipping_bracket.weight_max_g * item.quantity for item in suborder.items)

    try:
        booked = get_bring_client().book_shipment(sender, recipient, bracket.bring_product_code, total_weight_g)
    except BringClientError as e:
        raise HTTPException(status_code=502, detail=f"Bring-feil: {e}")

    label = ShippingLabel(
        seller_suborder_id=suborder.id,
        bring_shipment_id=booked.bring_shipment_id,
        tracking_number=booked.tracking_number,
        label_url=booked.label_url,
        postage_cost=booked.postage_cost,
    )
    db.add(label)
    suborder.shipping_bracket_id = bracket.id
    db.commit()

    return _label_public(label)
