import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship

from models.base import Base


class CommissionEntryStatus(str, enum.Enum):
    OWED = "owed"  # opparbeidet, ikke trukket ennå
    SETTLED = "settled"  # automatisk trekk lyktes
    RETRYING = "retrying"  # trekk feilet, forsøkes på nytt
    UNCOLLECTIBLE = "uncollectible"  # gitt opp etter gjentatt svikt -- se SPEC.md 3.1 dunning-policy


class CommissionLedger(Base):
    """Sporer plattformens provisjonskrav på Vipps-delbetalinger -- pengene
    gikk direkte til selgeren i selve transaksjonen, så dette er en
    fordring, ikke en allerede-mottatt inntekt. Stripe-salg trenger IKKE
    en rad her, siden provisjonen trekkes automatisk i selve
    Transfer-operasjonen. Se SPEC.md 3.1/3.4 for oppgjørsmekanismen
    (lagret betalingsmetode + periodisk automatisk trekk) og
    dunning-policyen (retry -> varsling -> midlertidig Vipps-deaktivering)."""

    __tablename__ = "commission_ledger"

    id = Column(Integer, primary_key=True, index=True)
    seller_suborder_id = Column(Integer, ForeignKey("seller_suborders.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)

    amount = Column(Float, nullable=False)
    status = Column(Enum(CommissionEntryStatus), nullable=False, default=CommissionEntryStatus.OWED)

    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)

    seller_suborder = relationship("SellerSubOrder")
    seller = relationship("Seller")
