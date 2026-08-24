from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class User(Base):
    """A single login identity. Either a platform-admin account, or a
    seller-side staff account (seller_id set) -- see SPEC.md 3.4/4.2: a
    user belongs to at most one seller at a time, so this is a plain FK,
    not a many-to-many membership table."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Platform-admin side (NorneTorg-ansatte). Independent of seller_id below --
    # a platform admin is never also a seller-side staff user.
    is_platform_admin = Column(Boolean, nullable=False, default=False)
    can_view_sellers = Column(Boolean, nullable=False, default=False)
    can_manage_sellers = Column(Boolean, nullable=False, default=False)
    can_view_transactions = Column(Boolean, nullable=False, default=False)
    can_manage_shipping_brackets = Column(Boolean, nullable=False, default=False)

    # Seller-side staff membership. NULL seller_id = not a seller-side user.
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=True)
    is_seller_owner = Column(Boolean, nullable=False, default=False)
    can_edit_products = Column(Boolean, nullable=False, default=False)
    can_view_orders = Column(Boolean, nullable=False, default=False)
    can_manage_payment_methods = Column(Boolean, nullable=False, default=False)
    can_manage_staff = Column(Boolean, nullable=False, default=False)

    seller = relationship("Seller", back_populates="staff", foreign_keys=[seller_id])
