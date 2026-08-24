from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.product import Product
from models.shipping import ShippingBracket
from routers.auth import require_platform_permission

router = APIRouter(prefix="/shipping-brackets", tags=["Shipping Brackets"])

_can_manage = [Depends(require_platform_permission("can_manage_shipping_brackets"))]


class ShippingBracketCreate(BaseModel):
    label: str
    weight_max_g: int
    max_dimension_sum_cm: int | None = None
    bring_product_code: str | None = None
    price_ex_vat: float = 0
    display_order: int = 0


class ShippingBracketUpdate(BaseModel):
    label: str | None = None
    weight_max_g: int | None = None
    max_dimension_sum_cm: int | None = None
    bring_product_code: str | None = None
    price_ex_vat: float | None = None
    display_order: int | None = None


def _public(bracket: ShippingBracket) -> dict:
    return {
        "id": bracket.id,
        "label": bracket.label,
        "weight_max_g": bracket.weight_max_g,
        "max_dimension_sum_cm": bracket.max_dimension_sum_cm,
        "bring_product_code": bracket.bring_product_code,
        "price_ex_vat": bracket.price_ex_vat,
        "display_order": bracket.display_order,
    }


@router.get("/")
def list_shipping_brackets(db: Session = Depends(get_db)):
    # Public: sellers need this to fill in the mandatory weight/dimension
    # field when creating a product -- see SPEC.md 3.2.
    brackets = db.query(ShippingBracket).order_by(ShippingBracket.display_order, ShippingBracket.weight_max_g).all()
    return [_public(b) for b in brackets]


@router.post("/", status_code=201, dependencies=_can_manage)
def create_shipping_bracket(payload: ShippingBracketCreate, db: Session = Depends(get_db)):
    bracket = ShippingBracket(**payload.model_dump())
    db.add(bracket)
    db.commit()
    db.refresh(bracket)
    return _public(bracket)


@router.put("/{bracket_id}", dependencies=_can_manage)
def update_shipping_bracket(bracket_id: int, payload: ShippingBracketUpdate, db: Session = Depends(get_db)):
    bracket = db.query(ShippingBracket).filter(ShippingBracket.id == bracket_id).first()
    if not bracket:
        raise HTTPException(status_code=404, detail="Fraktkategori ikke funnet")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(bracket, field, value)

    db.commit()
    db.refresh(bracket)
    return _public(bracket)


@router.delete("/{bracket_id}", dependencies=_can_manage)
def delete_shipping_bracket(bracket_id: int, db: Session = Depends(get_db)):
    bracket = db.query(ShippingBracket).filter(ShippingBracket.id == bracket_id).first()
    if not bracket:
        raise HTTPException(status_code=404, detail="Fraktkategori ikke funnet")

    if db.query(Product).filter(Product.shipping_bracket_id == bracket_id).first():
        raise HTTPException(status_code=400, detail="Kan ikke slette en fraktkategori som er i bruk av produkter")

    db.delete(bracket)
    db.commit()
    return {"status": "deleted", "id": bracket_id}
