import stripe

from celery_app import celery_app
from database import SessionLocal
from models.order import CartOrder, SellerSubOrderStatus
from models.payment import Payment
from utils.env import settings


def execute_seller_transfers(db, cart_order_id: int) -> None:
    """The actual money-movement step after a Stripe payment for a whole
    cart succeeds: one Transfer per seller-suborder, moving their subtotal
    minus the platform's flat commission (SPEC.md 3.3 punkt 1) to their
    connected Stripe account. Split out as a plain function (not just the
    Celery task body) so it's directly callable in tests without a broker."""
    stripe.api_key = settings.STRIPE_SECRET_KEY

    cart_order = db.query(CartOrder).filter(CartOrder.id == cart_order_id).first()
    if not cart_order:
        return

    for suborder in cart_order.seller_suborders:
        if suborder.status == SellerSubOrderStatus.PAID:
            continue  # already processed -- webhook retries must be idempotent

        seller_amount = round(suborder.subtotal_amount * (1 - settings.PLATFORM_COMMISSION_RATE), 2)

        try:
            transfer = stripe.Transfer.create(
                amount=int(round(seller_amount * 100)),
                currency="nok",
                destination=suborder.seller.stripe_account_id,
                transfer_group=f"cart_order_{cart_order.id}",
            )
        except stripe.error.StripeError as e:
            # Leave this suborder PENDING_PAYMENT-adjacent (not PAID) so it's
            # visible for manual follow-up -- the customer already paid, so
            # silently losing track of an unpaid-out seller would be worse
            # than a visibly stuck one.
            db.add(
                Payment(
                    seller_suborder_id=suborder.id,
                    provider="stripe",
                    status="failed",
                    amount=seller_amount,
                    currency="NOK",
                    external_reference=str(e),
                )
            )
            continue

        db.add(
            Payment(
                seller_suborder_id=suborder.id,
                provider="stripe",
                status="completed",
                amount=seller_amount,
                currency="NOK",
                external_reference=transfer.id,
            )
        )
        suborder.status = SellerSubOrderStatus.PAID

    db.commit()


@celery_app.task(name="tasks.create_seller_transfers")
def create_seller_transfers(cart_order_id: int) -> None:
    db = SessionLocal()
    try:
        execute_seller_transfers(db, cart_order_id)
    finally:
        db.close()
