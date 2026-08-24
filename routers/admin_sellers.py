from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.seller import Seller, SellerStatus
from routers.auth import require_platform_permission

router = APIRouter(prefix="/admin/sellers", tags=["Admin Sellers"])

_can_view = [Depends(require_platform_permission("can_view_sellers"))]
_can_manage = [Depends(require_platform_permission("can_manage_sellers"))]


def _public(seller: Seller) -> dict:
    return {
        "id": seller.id,
        "store_name": seller.store_name,
        "slug": seller.slug,
        "status": seller.status.value,
        "email_verified_at": seller.email_verified_at,
        "created_at": seller.created_at,
        "stripe_onboarding_complete": seller.stripe_onboarding_complete,
        "vipps_onboarding_complete": seller.vipps_onboarding_complete,
        "vipps_suspended_for_unpaid_commission": seller.vipps_suspended_for_unpaid_commission,
    }


@router.get("/", dependencies=_can_view)
def list_sellers(db: Session = Depends(get_db)):
    sellers = db.query(Seller).order_by(Seller.created_at.desc(), Seller.id.desc()).all()
    return [_public(s) for s in sellers]


@router.patch("/{seller_id}/suspend", dependencies=_can_manage)
def suspend_seller(seller_id: int, db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Selger ikke funnet")
    if seller.status != SellerStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Kun aktive selgere kan suspenderes")

    seller.status = SellerStatus.SUSPENDED
    db.commit()
    db.refresh(seller)
    return _public(seller)


@router.patch("/{seller_id}/reactivate", dependencies=_can_manage)
def reactivate_seller(seller_id: int, db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Selger ikke funnet")
    if seller.status != SellerStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="Kun suspenderte selgere kan reaktiveres")

    seller.status = SellerStatus.ACTIVE
    db.commit()
    db.refresh(seller)
    return _public(seller)
