import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class CartOrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PARTIALLY_PAID = "partially_paid"  # Vipps-flerselger-kurv med noen, men ikke alle, delordre betalt
    PAID = "paid"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SellerSubOrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CartOrder(Base):
    """Den overordnede handlekurv-ordren fra SPEC.md 4.1 -- kan spenne over
    flere selgere. Selve betalingsstatusen leves ut på SellerSubOrder-nivå;
    denne radens status er avledet (PARTIALLY_PAID / PAID) fra
    delordrene, ikke satt direkte av en betalingswebhook."""

    __tablename__ = "cart_orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_email = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    shipping_address = Column(String, nullable=True)
    shipping_zip = Column(String, nullable=True)
    shipping_city = Column(String, nullable=True)

    status = Column(Enum(CartOrderStatus), nullable=False, default=CartOrderStatus.PENDING_PAYMENT)

    # "stripe": kunden betaler hele handlekurven i én operasjon (PaymentIntent
    # + interne Transfer-objekter per selger-delordre).
    # "vipps": kunden betaler én delbetaling per selger, se SellerSubOrder.
    payment_provider = Column(String, nullable=False)

    # Opakt token utstedt ved betalingsinitiering, kreves for å sjekke
    # ordrestatus -- samme mønster som lukket enumereringssårbarheten i
    # Vitalityboost sitt betalingsstatus-endepunkt. CartOrder.id alene er
    # en sekvensiell int og aldri nok til å lese status.
    status_token = Column(String, nullable=True, index=True)

    total_amount = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Delt Stripe-betaling for hele handlekurven (kun relevant når
    # payment_provider == "stripe"). Selve splittingen til hver selger
    # skjer via egne Transfer-objekter sporet på SellerSubOrder/Payment.
    stripe_payment_intent_id = Column(String, nullable=True)

    seller_suborders = relationship(
        "SellerSubOrder", back_populates="cart_order", cascade="all, delete-orphan"
    )


class SellerSubOrder(Base):
    """Én per selger i handlekurven -- bærer sin egen betalingsstatus,
    lagerreservasjon og fraktetikett uavhengig av søsken-delordrene.
    Se SPEC.md 3.1/4.1 for hvorfor dette må være granulært på selger-nivå
    (spesielt for Vipps, som ikke støtter multi-part splitting)."""

    __tablename__ = "seller_suborders"

    id = Column(Integer, primary_key=True, index=True)
    cart_order_id = Column(Integer, ForeignKey("cart_orders.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)

    subtotal_amount = Column(Float, nullable=False, default=0)
    status = Column(Enum(SellerSubOrderStatus), nullable=False, default=SellerSubOrderStatus.PENDING_PAYMENT)

    shipping_bracket_id = Column(Integer, ForeignKey("shipping_brackets.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    cart_order = relationship("CartOrder", back_populates="seller_suborders")
    seller = relationship("Seller")
    items = relationship("OrderItem", back_populates="seller_suborder", cascade="all, delete-orphan")
    shipping_label = relationship("ShippingLabel", back_populates="seller_suborder", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    seller_suborder_id = Column(Integer, ForeignKey("seller_suborders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(Float, nullable=False, default=0)

    seller_suborder = relationship("SellerSubOrder", back_populates="items")
    product = relationship("Product")
