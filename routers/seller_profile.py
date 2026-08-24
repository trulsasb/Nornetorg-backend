from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.seller import Seller
from models.user import User
from routers.auth import get_current_seller_user, require_seller_permission

router = APIRouter(prefix="/sellers/profile", tags=["Seller Profile"])


class UpdateProfileRequest(BaseModel):
    business_address: str | None = None
    business_zip: str | None = None
    business_city: str | None = None


def _public(seller: Seller) -> dict:
    return {
        "store_name": seller.store_name,
        "slug": seller.slug,
        "business_address": seller.business_address,
        "business_zip": seller.business_zip,
        "business_city": seller.business_city,
    }


@router.get("/")
def get_profile(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.id == current_user.seller_id).first()
    return _public(seller)


@router.put("/", dependencies=[Depends(require_seller_permission("can_edit_products"))])
def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    seller = db.query(Seller).filter(Seller.id == current_user.seller_id).first()
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(seller, field, value)
    db.commit()
    db.refresh(seller)
    return _public(seller)
