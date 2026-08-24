from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class Payment(Base):
    """Én rad per selger-delordre, uansett betalingsleverandør -- se
    SPEC.md 4.1 for begrunnelsen: selv Stripe-splitting er i praksis én
    delt PaymentIntent + separate Transfer-objekter, så dette gir en
    ensartet betalingsstatus-modell per selger uavhengig av leverandør.

    "stripe": external_reference peker på Transfer-id (PaymentIntent-id
              ligger på selve CartOrder, delt mellom alle delordre).
    "vipps":  external_reference peker på Vipps' egen reference for denne
              spesifikke delbetalingen.
    """

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    seller_suborder_id = Column(Integer, ForeignKey("seller_suborders.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    provider = Column(String, nullable=False)  # "stripe" | "vipps"
    status = Column(String, nullable=False, default="pending")  # pending | completed | failed

    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="NOK")
    external_reference = Column(String, nullable=True, index=True)

    seller_suborder = relationship("SellerSubOrder")
    events = relationship("PaymentEvent", back_populates="payment", cascade="all, delete-orphan")


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    event_type = Column(String, nullable=False)
    data = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    payment = relationship("Payment", back_populates="events")
