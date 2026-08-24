from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import update
from sqlalchemy.orm import Session

from database import get_db
from models.order import CartOrder, CartOrderStatus, OrderItem, SellerSubOrder, SellerSubOrderStatus
from models.product import Product
from models.seller import Seller, SellerStatus

router = APIRouter(prefix="/checkout", tags=["Checkout"])


class CheckoutItem(BaseModel):
    product_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem]
    customer_name: str
    customer_email: EmailStr
    shipping_address: str
    shipping_zip: str
    shipping_city: str
    payment_provider: str  # "stripe" | "vipps"


def _try_reserve_stock(db: Session, product_id: int, quantity: int) -> bool:
    """Atomically decrements stock, but only if enough is still available --
    a conditional UPDATE re-checks the live row instead of trusting an
    earlier Python-side read, which is what lets two concurrent checkouts
    both pass validation and both decrement the same unit. Same pattern
    fixed in Vitalityboost after a real race-condition bug there."""
    result = db.execute(
        update(Product)
        .where(Product.id == product_id, Product.stock >= quantity)
        .values(stock=Product.stock - quantity)
    )
    return result.rowcount == 1


@router.post("/", status_code=201)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Handlekurven er tom")
    if payload.payment_provider not in ("stripe", "vipps"):
        raise HTTPException(status_code=400, detail="Ugyldig betalingsmetode")

    for field_name, value in [
        ("customer_name", payload.customer_name),
        ("shipping_address", payload.shipping_address),
        ("shipping_zip", payload.shipping_zip),
        ("shipping_city", payload.shipping_city),
    ]:
        if not value or not value.strip():
            raise HTTPException(status_code=400, detail=f"{field_name} er påkrevd")

    # Same visibility rule as the public catalog (Modul 5) -- a product
    # that isn't publicly visible (inactive, or its seller not ACTIVE)
    # can't be bought either, no separate copy of this rule to drift out
    # of sync with what the catalog actually shows.
    product_ids = [item.product_id for item in payload.items]
    products = {
        p.id: p
        for p in (
            db.query(Product)
            .join(Seller, Product.seller_id == Seller.id)
            .filter(Product.id.in_(product_ids), Product.active.is_(True), Seller.status == SellerStatus.ACTIVE)
            .all()
        )
    }

    # Fast preliminary check -- gives a specific, friendly error for the
    # common case. Not authoritative under concurrency; the atomic
    # reservation loop below is what actually enforces it.
    for item in payload.items:
        product = products.get(item.product_id)
        if not product:
            raise HTTPException(status_code=400, detail=f"Produkt {item.product_id} finnes ikke")
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Ugyldig antall for produkt {item.product_id}")
        if product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Ikke nok på lager for {product.name}")

    items_by_seller: dict[int, list[CheckoutItem]] = defaultdict(list)
    for item in payload.items:
        items_by_seller[products[item.product_id].seller_id].append(item)

    # Every seller in the cart must actually be able to RECEIVE money via
    # the chosen provider -- a cart could otherwise be paid for and land on
    # a seller who never finished onboarding, with no way to pay them out.
    # NOTE: Vipps is NOT restricted to single-seller carts -- see SPEC.md 3.1.
    # A multi-seller Vipps cart is split into one sub-payment per seller
    # (Modul 8 builds the actual per-seller payment flow); this endpoint
    # only needs to confirm every seller involved can receive Vipps at all.
    involved_sellers = {sid: products[items[0].product_id].seller for sid, items in items_by_seller.items()}
    if payload.payment_provider == "stripe":
        not_ready = [s.store_name for s in involved_sellers.values() if not s.stripe_onboarding_complete]
        if not_ready:
            raise HTTPException(
                status_code=400,
                detail=f"Følgende selger(e) har ikke fullført Stripe-tilkobling ennå: {', '.join(not_ready)}",
            )
    else:  # vipps
        not_ready = [s.store_name for s in involved_sellers.values() if not s.vipps_onboarding_complete]
        if not_ready:
            raise HTTPException(
                status_code=400, detail=f"Følgende selger(e) har ikke koblet til Vipps ennå: {', '.join(not_ready)}"
            )
        suspended = [s.store_name for s in involved_sellers.values() if s.vipps_suspended_for_unpaid_commission]
        if suspended:
            raise HTTPException(
                status_code=400,
                detail=f"Følgende selger(e) kan ikke motta Vipps-betaling akkurat nå: {', '.join(suspended)}",
            )
        # Vipps commission is never collected in the transaction itself
        # (Modul 8/10) -- a seller must have a way to actually PAY it before
        # they're allowed to accept Vipps money at all, or the debt could
        # start accumulating with no collection mechanism in place yet.
        no_payment_method = [
            s.store_name for s in involved_sellers.values() if not s.commission_payment_method_id
        ]
        if no_payment_method:
            raise HTTPException(
                status_code=400,
                detail=f"Følgende selger(e) har ikke satt opp betalingsmetode for provisjon: {', '.join(no_payment_method)}",
            )

    total_amount = sum(products[item.product_id].price * item.quantity for item in payload.items)

    cart_order = CartOrder(
        customer_name=payload.customer_name.strip(),
        customer_email=payload.customer_email,
        shipping_address=payload.shipping_address.strip(),
        shipping_zip=payload.shipping_zip.strip(),
        shipping_city=payload.shipping_city.strip(),
        status=CartOrderStatus.PENDING_PAYMENT,
        payment_provider=payload.payment_provider,
        total_amount=total_amount,
    )
    db.add(cart_order)
    db.flush()  # assigns cart_order.id without committing, in case a reservation below fails

    seller_suborders_response = []

    for seller_id, seller_items in items_by_seller.items():
        subtotal = sum(products[item.product_id].price * item.quantity for item in seller_items)

        suborder = SellerSubOrder(
            cart_order_id=cart_order.id,
            seller_id=seller_id,
            subtotal_amount=subtotal,
            status=SellerSubOrderStatus.PENDING_PAYMENT,
            # shipping_bracket_id left unset here -- aggregating this
            # seller's items into an actual freight bracket is Modul 9's
            # job (fraktberegner), not part of cart/order creation.
        )
        db.add(suborder)
        db.flush()

        for item in seller_items:
            product = products[item.product_id]
            if not _try_reserve_stock(db, item.product_id, item.quantity):
                db.rollback()
                raise HTTPException(status_code=409, detail=f"Ikke nok på lager for {product.name} (solgt i mellomtiden)")
            db.add(
                OrderItem(
                    seller_suborder_id=suborder.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price_at_purchase=product.price,
                )
            )

        seller_suborders_response.append(
            {
                "seller_id": seller_id,
                "store_name": products[seller_items[0].product_id].seller.store_name,
                "subtotal_amount": subtotal,
                "status": suborder.status.value,
            }
        )

    db.commit()
    db.refresh(cart_order)

    return {
        "cart_order_id": cart_order.id,
        "status": cart_order.status.value,
        "payment_provider": cart_order.payment_provider,
        "total_amount": cart_order.total_amount,
        "seller_suborders": seller_suborders_response,
    }
