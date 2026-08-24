from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import Base


class ShippingBracket(Base):
    """Posten Norge/Bring's weight+dimension parcel tiers, mirrored as data
    rather than a hardcoded enum -- Bring can change their categories and
    prices, and a platform admin needs to be able to update this without a
    code deploy. See SPEC.md 3.2/4.4. Exact bracket boundaries and
    bring_product_code values must be verified against Bring's current API
    docs when Modul 9 (fraktberegner) is built -- nothing here is real data
    yet, this is only the table shape."""

    __tablename__ = "shipping_brackets"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)  # e.g. "Liten pakke, inntil 1 kg"
    weight_max_g = Column(Integer, nullable=False)
    max_dimension_sum_cm = Column(Integer, nullable=True)
    bring_product_code = Column(String, nullable=True)
    price_ex_vat = Column(Float, nullable=False, default=0)
    display_order = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    products = relationship("Product", back_populates="shipping_bracket")


class ShippingLabel(Base):
    """Kjøpt fraktetikett/porto for én selger-delordre, via Bring API --
    se SPEC.md 4.4. Én rad per faktisk kjøpt etikett (skulle en selger
    trenge å kjøpe på nytt pga. feil, blir det en ny rad, ikke en
    overskrevet en -- bevarer kjøpshistorikk/kvittering)."""

    __tablename__ = "shipping_labels"

    id = Column(Integer, primary_key=True, index=True)
    seller_suborder_id = Column(Integer, ForeignKey("seller_suborders.id"), nullable=False)
    bring_shipment_id = Column(String, nullable=True)
    tracking_number = Column(String, nullable=True)
    label_url = Column(String, nullable=True)
    postage_cost = Column(Float, nullable=False, default=0)
    purchased_at = Column(DateTime, default=datetime.utcnow)

    seller_suborder = relationship("SellerSubOrder", back_populates="shipping_label")
