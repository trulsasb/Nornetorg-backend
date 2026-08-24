from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.commission import CommissionLedger
from models.user import User
from routers.auth import get_current_seller_user, require_platform_permission

router = APIRouter(tags=["Commission"])


def _public(row: CommissionLedger) -> dict:
    return {
        "id": row.id,
        "seller_suborder_id": row.seller_suborder_id,
        "amount": row.amount,
        "status": row.status.value,
        "retry_count": row.retry_count,
        "created_at": row.created_at,
        "settled_at": row.settled_at,
    }


@router.get("/sellers/commission")
def list_own_commission(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    rows = db.query(CommissionLedger).filter(CommissionLedger.seller_id == current_user.seller_id).all()
    return [_public(r) for r in rows]


@router.get("/admin/commission", dependencies=[Depends(require_platform_permission("can_view_transactions"))])
def list_all_commission(db: Session = Depends(get_db)):
    rows = db.query(CommissionLedger).all()
    return [{**_public(r), "seller_id": r.seller_id} for r in rows]
