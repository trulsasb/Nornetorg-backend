from sqlalchemy import Column, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from models.base import Base


class Category(Base):
    """attribute_schema describes the extra, category-specific product
    fields a seller fills in (e.g. clothing: size/color; electronics:
    specs) -- see SPEC.md 4.3. Kept generic (JSON) rather than a fixed
    schema since categories span arbitrary industries."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    attribute_schema = Column(JSON, nullable=True)

    children = relationship("Category", backref="parent", remote_side=[id])
