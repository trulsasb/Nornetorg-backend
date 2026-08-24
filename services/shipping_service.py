from sqlalchemy.orm import Session

from models.order import SellerSubOrder
from models.shipping import ShippingBracket


def aggregate_shipping_bracket(db: Session, seller_suborder: SellerSubOrder) -> ShippingBracket | None:
    """Determines the effective ShippingBracket for a whole seller-parcel
    (all items in one seller's portion of a cart, since each seller ships
    their own package -- see SPEC.md 3.2/4.4).

    Products only record a WEIGHT BRACKET (a checkbox tier), not an exact
    gram value -- that was a deliberate SPEC.md 3.2 choice to keep product
    registration low-friction for sellers. So this aggregation necessarily
    approximates: it sums each item's bracket's weight_max_g (the upper
    bound of its tier) times quantity, then picks the smallest bracket that
    can hold that sum. This slightly OVER-estimates true weight (real
    weight <= bracket max), which is the conservatively safe direction for
    a shipping cost estimate -- never undercharges postage.

    Returns None if the aggregate exceeds every available bracket, so the
    caller can surface that for manual handling rather than silently
    picking an insufficient bracket."""
    total_weight_g = sum(item.product.shipping_bracket.weight_max_g * item.quantity for item in seller_suborder.items)

    return (
        db.query(ShippingBracket)
        .filter(ShippingBracket.weight_max_g >= total_weight_g)
        .order_by(ShippingBracket.weight_max_g.asc())
        .first()
    )
