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
