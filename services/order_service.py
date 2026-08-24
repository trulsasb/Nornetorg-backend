from sqlalchemy.orm import Session

from models.order import CartOrder, CartOrderStatus, SellerSubOrder, SellerSubOrderStatus
from models.product import Product


def release_failed_cart_order(db: Session, cart_order_id: int) -> None:
    """Undoes the stock reservation made at checkout time (Modul 6) when a
    Stripe payment never completes. Guarded on PENDING_PAYMENT so a
    duplicate webhook delivery -- which Stripe explicitly doesn't guarantee
    against -- can't restore stock twice. Restores ALL seller-suborders'
    items together, since a Stripe cart is one unified payment; there's no
    partial-failure state for Stripe the way there is for Vipps (Modul 8)."""
    cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first()
    if not cart_order or cart_order.status != CartOrderStatus.PENDING_PAYMENT:
        return

    for suborder in cart_order.seller_suborders:
        for item in suborder.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity
        suborder.status = SellerSubOrderStatus.FAILED

    cart_order.status = CartOrderStatus.FAILED


def release_failed_seller_suborder(db: Session, seller_suborder_id: int) -> None:
    """Vipps equivalent of release_failed_cart_order, but scoped to ONE
    seller-suborder -- see SPEC.md 3.1/4.1. A Vipps cart splits into
    independent per-seller sub-payments, so only the failed seller's items
    are released; other sellers' suborders in the same cart may already be
    paid or still pending and must not be touched. Guarded on
    PENDING_PAYMENT for the same duplicate-webhook-delivery reason."""
    suborder = db.query(SellerSubOrder).filter(SellerSubOrder.id == seller_suborder_id).first()
    if not suborder or suborder.status != SellerSubOrderStatus.PENDING_PAYMENT:
        return

    for item in suborder.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity
    suborder.status = SellerSubOrderStatus.FAILED

    recompute_cart_order_status(suborder.cart_order)


def recompute_cart_order_status(cart_order: CartOrder) -> None:
    """Derives CartOrder.status from its seller-suborders' individual
    statuses -- see SPEC.md 3.1: a Vipps cart needs an explicit
    "delvis betalt" state since sellers are paid independently. Idempotent,
    safe to call repeatedly as suborders settle one at a time."""
    statuses = [s.status for s in cart_order.seller_suborders]
    if all(s == SellerSubOrderStatus.PAID for s in statuses):
        cart_order.status = CartOrderStatus.PAID
    elif any(s == SellerSubOrderStatus.PAID for s in statuses):
        cart_order.status = CartOrderStatus.PARTIALLY_PAID
    elif all(s == SellerSubOrderStatus.FAILED for s in statuses):
        cart_order.status = CartOrderStatus.FAILED
    # else: some still PENDING_PAYMENT and none PAID yet -- leave as-is
