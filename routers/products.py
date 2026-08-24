from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.category import Category
from models.product import Product, ProductImage
from models.shipping import ShippingBracket
from models.user import User
from routers.auth import get_current_seller_user, require_seller_permission
from utils.slugify import slugify

router = APIRouter(prefix="/sellers/products", tags=["Seller Products"])

# Kun redigering (opprett/endre/slett) er rettighetsstyrt -- å SE egen
# butikks produktliste er ikke en egen sperret handling, tilsvarende
# hvordan "egen butikks ansatte"-listen i Modul 2 er åpen for alle ansatte.
_can_edit = [Depends(require_seller_permission("can_edit_products"))]


class ProductCreate(BaseModel):
    name: str
    category_id: int
    shipping_bracket_id: int
    description: str | None = None
    price: float
    stock: int = 0
    attributes: dict | None = None
    active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    shipping_bracket_id: int | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None
    attributes: dict | None = None
    active: bool | None = None


class AddImageRequest(BaseModel):
    url: str
    display_order: int = 0


def _validate_attributes(attributes: dict | None, schema: dict | None) -> None:
    """Lightweight validation against Category.attribute_schema -- see
    SPEC.md 4.3. schema shape: {"field_name": {"type": "string"|"number"|"boolean", "required": bool}}."""
    if not schema:
        return
    attributes = attributes or {}
    type_map = {"string": str, "number": (int, float), "boolean": bool}
    for field_name, spec in schema.items():
        required = spec.get("required", False)
        if field_name not in attributes:
            if required:
                raise HTTPException(status_code=400, detail=f"Mangler påkrevd attributt: {field_name}")
            continue
        expected_type = spec.get("type")
        py_type = type_map.get(expected_type)
        if py_type and not isinstance(attributes[field_name], py_type):
            raise HTTPException(status_code=400, detail=f"Attributt '{field_name}' skal være av type {expected_type}")


def _public(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "category_id": product.category_id,
        "shipping_bracket_id": product.shipping_bracket_id,
        "description": product.description,
        "price": product.price,
        "stock": product.stock,
        "active": product.active,
        "attributes": product.attributes,
        "images": [{"id": i.id, "url": i.url, "display_order": i.display_order} for i in product.images],
    }


def _get_own_product(product_id: int, current_user: User, db: Session) -> Product:
    # seller_id filter is the tenant boundary -- a product id alone is
    # never enough, it must also belong to the caller's own seller.
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.seller_id == current_user.seller_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produkt ikke funnet")
    return product


@router.get("/")
def list_own_products(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.seller_id == current_user.seller_id).all()
    return [_public(p) for p in products]


@router.get("/{product_id}")
def get_own_product(
    product_id: int, current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    return _public(_get_own_product(product_id, current_user, db))


@router.post("/", status_code=201, dependencies=_can_edit)
def create_product(
    payload: ProductCreate, current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    if payload.price <= 0:
        raise HTTPException(status_code=400, detail="Pris må være positiv")
    if payload.stock < 0:
        raise HTTPException(status_code=400, detail="Lager kan ikke være negativt")

    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="category_id peker på en kategori som ikke finnes")
    if not db.query(ShippingBracket).filter(ShippingBracket.id == payload.shipping_bracket_id).first():
        raise HTTPException(status_code=400, detail="shipping_bracket_id peker på en fraktkategori som ikke finnes")

    _validate_attributes(payload.attributes, category.attribute_schema)

    base_slug = slugify(payload.name)
    slug = base_slug
    suffix = 1
    while (
        db.query(Product)
        .filter(Product.seller_id == current_user.seller_id, Product.slug == slug)
        .first()
    ):
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    product = Product(
        seller_id=current_user.seller_id,
        category_id=payload.category_id,
        shipping_bracket_id=payload.shipping_bracket_id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        price=payload.price,
        stock=payload.stock,
        attributes=payload.attributes,
        active=payload.active,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _public(product)


@router.put("/{product_id}", dependencies=_can_edit)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    product = _get_own_product(product_id, current_user, db)
    data = payload.model_dump(exclude_unset=True)

    if "price" in data and data["price"] <= 0:
        raise HTTPException(status_code=400, detail="Pris må være positiv")
    if "stock" in data and data["stock"] < 0:
        raise HTTPException(status_code=400, detail="Lager kan ikke være negativt")

    target_category_id = data.get("category_id", product.category_id)
    category = db.query(Category).filter(Category.id == target_category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="category_id peker på en kategori som ikke finnes")

    if "shipping_bracket_id" in data:
        if not db.query(ShippingBracket).filter(ShippingBracket.id == data["shipping_bracket_id"]).first():
            raise HTTPException(status_code=400, detail="shipping_bracket_id peker på en fraktkategori som ikke finnes")

    if "attributes" in data or "category_id" in data:
        _validate_attributes(data.get("attributes", product.attributes), category.attribute_schema)

    for field, value in data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return _public(product)


@router.delete("/{product_id}", dependencies=_can_edit)
def delete_product(
    product_id: int, current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)
):
    product = _get_own_product(product_id, current_user, db)
    db.delete(product)
    db.commit()
    return {"status": "deleted", "id": product_id}


# ---------------------------------------------------------
# PRODUCT IMAGES -- plain URLs for now, no upload/storage infra built yet
# (mirrors the deferred picture-upload decision from Vitalityboost -- needs
# real object storage like R2/Cloudinary before a real upload endpoint
# makes sense; sellers provide externally-hosted URLs in the meantime)
# ---------------------------------------------------------


@router.post("/{product_id}/images", status_code=201, dependencies=_can_edit)
def add_product_image(
    product_id: int,
    payload: AddImageRequest,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    product = _get_own_product(product_id, current_user, db)
    image = ProductImage(product_id=product.id, url=payload.url, display_order=payload.display_order)
    db.add(image)
    db.commit()
    db.refresh(image)
    return {"id": image.id, "url": image.url, "display_order": image.display_order}


@router.delete("/{product_id}/images/{image_id}", dependencies=_can_edit)
def delete_product_image(
    product_id: int,
    image_id: int,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    product = _get_own_product(product_id, current_user, db)
    image = db.query(ProductImage).filter(ProductImage.id == image_id, ProductImage.product_id == product.id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Bilde ikke funnet")
    db.delete(image)
    db.commit()
    return {"status": "deleted", "id": image_id}
