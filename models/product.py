from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from models.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Slug er unikt PER SELGER, ikke globalt -- to selgere kan begge ha
        # et produkt som heter "t-skjorte". Offentlig URL scopes uansett
        # med butikkens slug (se Modul 5).
        UniqueConstraint("seller_id", "slug", name="uq_product_seller_slug"),
    )

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Obligatorisk på alle produkter uansett kategori -- se SPEC.md 3.2/4.3.
    # Avkrysning mot ShippingBracket, ikke fritekst.
    shipping_bracket_id = Column(Integer, ForeignKey("shipping_brackets.id"), nullable=False)

    # Kategori-spesifikke attributter (størrelse, farge, spesifikasjoner osv.)
    # -- se Category.attribute_schema for malen dette skal fylle ut mot.
    attributes = Column(JSON, nullable=True)

    seller = relationship("Seller")
    category = relationship("Category")
    shipping_bracket = relationship("ShippingBracket", back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    url = Column(String, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="images")
