import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class SellerStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Seller(Base):
    __tablename__ = "sellers"

    id = Column(Integer, primary_key=True, index=True)
    store_name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    status = Column(Enum(SellerStatus), nullable=False, default=SellerStatus.PENDING_VERIFICATION)
    email_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Returadresse -- påkrevd for å faktisk kunne kjøpe porto/etikett hos
    # Bring (Modul 9). Nullable siden den ikke finnes ved registrering;
    # settes via PUT /sellers/profile før første etikettkjøp.
    business_address = Column(String, nullable=True)
    business_zip = Column(String, nullable=True)
    business_city = Column(String, nullable=True)

    # Stripe Connect (Express) -- for RECEIVING payment splits. See SPEC.md 3.4.
    stripe_account_id = Column(String, nullable=True)
    stripe_onboarding_complete = Column(Boolean, nullable=False, default=False)

    # Vipps -- selgerens egen avtale, kryptert med SETTINGS_ENCRYPTION_KEY.
    # Lagres som chiffertekst i disse kolonnene, aldri i klartekst.
    vipps_client_id_encrypted = Column(String, nullable=True)
    vipps_client_secret_encrypted = Column(String, nullable=True)
    vipps_subscription_key_encrypted = Column(String, nullable=True)
    vipps_msn_encrypted = Column(String, nullable=True)
    # Returned when the seller registers a webhook via Vipps' POST /webhooks
    # -- each seller has their OWN Vipps agreement, so each needs their own
    # webhook secret, unlike Vitalityboost's single platform-wide one.
    vipps_webhook_secret_encrypted = Column(String, nullable=True)
    vipps_onboarding_complete = Column(Boolean, nullable=False, default=False)

    # Midlertidig deaktivering av Vipps ved vedvarende mislykket provisjonstrekk
    # -- se SPEC.md 3.1 dunning-policy. Stripe-salg er upåvirket av dette flagget.
    vipps_suspended_for_unpaid_commission = Column(Boolean, nullable=False, default=False)

    # Plattformens EGEN Stripe-integrasjon for å TREKKE provisjon fra selgeren
    # -- se models/commission.py. Adskilt fra stripe_account_id over, som er
    # selgerens EGEN Connect-konto for å MOTTA utbetaling. commission_stripe_customer_id
    # er en Stripe Customer på plattformens hovedkonto; commission_payment_method_id
    # er kortet/betalingsmetoden festet til den kunden.
    commission_stripe_customer_id = Column(String, nullable=True)
    commission_payment_method_id = Column(String, nullable=True)

    staff = relationship("User", back_populates="seller", foreign_keys="User.seller_id")
