import asyncio
from datetime import datetime

import stripe

from celery_app import celery_app
from database import SessionLocal
from models.commission import CommissionEntryStatus, CommissionLedger
from models.seller import Seller
from services.email_service import EmailService, build_commission_draw_failed_email
from utils.env import settings


def draw_commission_for_seller(db, seller: Seller) -> None:
    """One seller's periodic Vipps-commission draw -- see SPEC.md 3.1. Sums
    every outstanding (OWED or RETRYING) ledger row into a single charge
    against the seller's stored payment method (Modul 3), rather than one
    charge per row, so a seller with several small unsettled sales gets one
    combined attempt instead of many.

    Dunning: on failure, every row in this batch has its retry_count
    incremented together (they're all part of the same collective attempt).
    Once ANY row's retry_count reaches DUNNING_MAX_RETRIES, Vipps is
    suspended for this seller specifically -- not the whole store, Stripe
    sales are unaffected -- until the debt is actually settled."""
    owed_rows = (
        db.query(CommissionLedger)
        .filter(
            CommissionLedger.seller_id == seller.id,
            CommissionLedger.status.in_([CommissionEntryStatus.OWED, CommissionEntryStatus.RETRYING]),
        )
        .all()
    )
    if not owed_rows:
        return

    total_owed = round(sum(row.amount for row in owed_rows), 2)
    if total_owed <= 0:
        return

    if not seller.commission_payment_method_id:
        _record_failed_attempt(db, seller, owed_rows, total_owed)
        return

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        stripe.PaymentIntent.create(
            amount=int(round(total_owed * 100)),
            currency="nok",
            customer=seller.commission_stripe_customer_id,
            payment_method=seller.commission_payment_method_id,
            off_session=True,
            confirm=True,
        )
    except stripe.error.StripeError:
        _record_failed_attempt(db, seller, owed_rows, total_owed)
        return

    for row in owed_rows:
        row.status = CommissionEntryStatus.SETTLED
        row.settled_at = datetime.utcnow()

    # Debt actually settled -- lift a prior dunning suspension, if any.
    # Never cleared any other way (see Modul 3's connect_vipps, which
    # deliberately leaves this flag untouched on reconnect).
    if seller.vipps_suspended_for_unpaid_commission:
        seller.vipps_suspended_for_unpaid_commission = False

    db.commit()


def _record_failed_attempt(db, seller: Seller, owed_rows: list[CommissionLedger], total_owed: float) -> None:
    attempt = max(row.retry_count for row in owed_rows) + 1
    will_suspend = attempt >= settings.DUNNING_MAX_RETRIES

    for row in owed_rows:
        row.retry_count = attempt
        row.status = CommissionEntryStatus.RETRYING

    if will_suspend:
        seller.vipps_suspended_for_unpaid_commission = True

    db.commit()

    subject, body = build_commission_draw_failed_email(
        seller.store_name, total_owed, attempt, settings.DUNNING_MAX_RETRIES, will_suspend
    )
    owner_email = next((u.email for u in seller.staff if u.is_seller_owner), None)
    if owner_email:
        asyncio.run(EmailService().send(owner_email, subject, body))


@celery_app.task(name="tasks.run_commission_draws")
def run_commission_draws() -> None:
    """Entry point for a periodic Celery Beat schedule (deployment-time
    configuration, not set up here) -- iterates every seller with any
    outstanding commission and attempts to draw it."""
    db = SessionLocal()
    try:
        seller_ids = [
            row.seller_id
            for row in db.query(CommissionLedger.seller_id)
            .filter(CommissionLedger.status.in_([CommissionEntryStatus.OWED, CommissionEntryStatus.RETRYING]))
            .distinct()
            .all()
        ]
        for seller_id in seller_ids:
            seller = db.query(Seller).filter(Seller.id == seller_id).first()
            if seller:
                draw_commission_for_seller(db, seller)
    finally:
        db.close()
