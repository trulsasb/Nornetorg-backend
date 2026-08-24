from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class StaffInvitation(Base):
    """Et pending-tilbud om å bli ansatt hos en selger -- se SPEC.md 3.4/4.2.
    Ingen User-rad opprettes før invitasjonen faktisk aksepteres (unngår
    halvferdige/passordløse brukerrader som aldri fullfører onboarding).
    Rettighetene som skal gis er lagret her og kopieres til User ved aksept."""

    __tablename__ = "staff_invitations"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)

    # Rettighetene den inviterte skal få ved aksept -- speiler de samme
    # feltene som User (unntatt is_seller_owner, som aldri gis via invitasjon).
    can_edit_products = Column(Boolean, nullable=False, default=False)
    can_view_orders = Column(Boolean, nullable=False, default=False)
    can_manage_payment_methods = Column(Boolean, nullable=False, default=False)
    can_manage_staff = Column(Boolean, nullable=False, default=False)

    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)

    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    seller = relationship("Seller")
