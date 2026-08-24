from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.category import Category
from models.product import Product, ProductImage
from models.seller import Seller, SellerStatus

router = APIRouter(prefix="/catalog", tags=["Public Catalog"])

# Separate "/catalog" prefix, distinct from the authenticated /sellers/products
# management endpoints (Modul 4) -- this router is entirely public and only
# ever exposes products from ACTIVE sellers, never pending/suspended ones.

_MAX_LIMIT = 100


def _visible_products_query(db: Session):
    return (
        db.query(Product)
        .join(Seller, Product.seller_id == Seller.id)
        .filter(Product.active.is_(True), Seller.status == SellerStatus.ACTIVE)
    )


def _product_summary(product: Product) -> dict:
    thumbnail = min(product.images, key=lambda i: i.display_order).url if product.images else None
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "price": product.price,
        "stock": product.stock,
        "thumbnail_url": thumbnail,
        "category": {"id": product.category.id, "name": product.category.name, "slug": product.category.slug},
        "seller": {"store_name": product.seller.store_name, "slug": product.seller.slug},
    }


def _product_detail(product: Product) -> dict:
    return {
        **_product_summary(product),
        "description": product.description,
        "attributes": product.attributes,
        "images": [
            {"url": i.url, "display_order": i.display_order}
            for i in sorted(product.images, key=lambda i: i.display_order)
        ],
    }


@router.get("/products")
def search_products(
    q: str | None = Query(default=None, description="Fritekstsøk i produktnavn"),
    category_id: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc)$"),
    limit: int = Query(default=20, le=_MAX_LIMIT, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = _visible_products_query(db)

    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    total = query.count()

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [_product_summary(p) for p in products],
    }


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = _visible_products_query(db).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produkt ikke funnet")
    return _product_detail(product)


@router.get("/stores")
def list_stores(
    limit: int = Query(default=20, le=_MAX_LIMIT, gt=0),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Seller).filter(Seller.status == SellerStatus.ACTIVE)
    total = query.count()
    sellers = query.order_by(Seller.store_name).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [{"store_name": s.store_name, "slug": s.slug} for s in sellers],
    }


@router.get("/stores/{seller_slug}")
def get_store(seller_slug: str, db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.slug == seller_slug, Seller.status == SellerStatus.ACTIVE).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Butikk ikke funnet")

    products = (
        db.query(Product)
        .filter(Product.seller_id == seller.id, Product.active.is_(True))
        .order_by(Product.created_at.desc())
        .all()
    )
    return {
        "store_name": seller.store_name,
        "slug": seller.slug,
        "products": [_product_summary(p) for p in products],
    }


@router.get("/stores/{seller_slug}/products/{product_slug}")
def get_store_product(seller_slug: str, product_slug: str, db: Session = Depends(get_db)):
    product = (
        _visible_products_query(db)
        .filter(Seller.slug == seller_slug, Product.slug == product_slug)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produkt ikke funnet")
    return _product_detail(product)
