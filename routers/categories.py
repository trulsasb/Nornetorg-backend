from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.category import Category
from models.product import Product
from routers.auth import require_platform_permission
from utils.slugify import slugify

router = APIRouter(prefix="/categories", tags=["Categories"])

_can_manage = [Depends(require_platform_permission("can_manage_categories"))]


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    attribute_schema: dict | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    attribute_schema: dict | None = None


def _public(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "parent_id": category.parent_id,
        "attribute_schema": category.attribute_schema,
    }


@router.get("/")
def list_categories(db: Session = Depends(get_db)):
    # Public: sellers need this to populate the product-creation form
    # before/without being fully onboarded, and it's harmless shared
    # reference data -- no seller- or customer-specific info here.
    categories = db.query(Category).order_by(Category.name).all()
    return [_public(c) for c in categories]


@router.post("/", status_code=201, dependencies=_can_manage)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if payload.parent_id is not None and not db.query(Category).filter(Category.id == payload.parent_id).first():
        raise HTTPException(status_code=400, detail="parent_id peker på en kategori som ikke finnes")

    base_slug = slugify(payload.name)
    slug = base_slug
    suffix = 1
    while db.query(Category).filter(Category.slug == slug).first():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    category = Category(
        name=payload.name, slug=slug, parent_id=payload.parent_id, attribute_schema=payload.attribute_schema
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return _public(category)


@router.put("/{category_id}", dependencies=_can_manage)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategori ikke funnet")

    if payload.parent_id is not None:
        if payload.parent_id == category_id:
            raise HTTPException(status_code=400, detail="En kategori kan ikke være sin egen foreldrekategori")
        if not db.query(Category).filter(Category.id == payload.parent_id).first():
            raise HTTPException(status_code=400, detail="parent_id peker på en kategori som ikke finnes")
        category.parent_id = payload.parent_id

    if payload.name is not None:
        category.name = payload.name
    if payload.attribute_schema is not None:
        category.attribute_schema = payload.attribute_schema

    db.commit()
    db.refresh(category)
    return _public(category)


@router.delete("/{category_id}", dependencies=_can_manage)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategori ikke funnet")

    if db.query(Category).filter(Category.parent_id == category_id).first():
        raise HTTPException(status_code=400, detail="Kan ikke slette en kategori som har underkategorier")

    if db.query(Product).filter(Product.category_id == category_id).first():
        raise HTTPException(status_code=400, detail="Kan ikke slette en kategori som har produkter")

    db.delete(category)
    db.commit()
    return {"status": "deleted", "id": category_id}
