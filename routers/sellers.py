import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models.invitation import StaffInvitation
from models.user import User
from routers.auth import get_current_seller_user, require_seller_permission
from services.email_service import EmailService, build_invitation_email
from utils.env import settings
from utils.tokens import INVITATION_EXPIRE_DAYS, hash_invitation_token

router = APIRouter(prefix="/sellers/staff", tags=["Seller Staff"])

_can_manage_staff = [Depends(require_seller_permission("can_manage_staff"))]


class InviteStaffRequest(BaseModel):
    email: EmailStr
    can_edit_products: bool = False
    can_view_orders: bool = False
    can_manage_payment_methods: bool = False
    can_manage_staff: bool = False


def _staff_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "is_seller_owner": user.is_seller_owner,
        "can_edit_products": user.can_edit_products,
        "can_view_orders": user.can_view_orders,
        "can_manage_payment_methods": user.can_manage_payment_methods,
        "can_manage_staff": user.can_manage_staff,
    }


@router.get("/")
def list_staff(current_user: User = Depends(get_current_seller_user), db: Session = Depends(get_db)):
    # seller_id comes from the authenticated user, never from a query param --
    # this is the tenant-isolation boundary from SPEC.md 4.2.
    staff = db.query(User).filter(User.seller_id == current_user.seller_id).all()
    return [_staff_public(u) for u in staff]


@router.post("/invite", status_code=201, dependencies=_can_manage_staff)
async def invite_staff(
    payload: InviteStaffRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="E-postadressen tilhører allerede en bruker")

    existing_invite = (
        db.query(StaffInvitation)
        .filter(
            StaffInvitation.email == payload.email,
            StaffInvitation.seller_id == current_user.seller_id,
            StaffInvitation.accepted_at.is_(None),
            StaffInvitation.revoked_at.is_(None),
        )
        .first()
    )
    if existing_invite and existing_invite.expires_at > datetime.utcnow():
        raise HTTPException(status_code=400, detail="Det finnes allerede en aktiv invitasjon til denne e-postadressen")

    raw_token = secrets.token_urlsafe(32)
    invitation = StaffInvitation(
        seller_id=current_user.seller_id,
        email=payload.email,
        can_edit_products=payload.can_edit_products,
        can_view_orders=payload.can_view_orders,
        can_manage_payment_methods=payload.can_manage_payment_methods,
        can_manage_staff=payload.can_manage_staff,
        invited_by_user_id=current_user.id,
        token_hash=hash_invitation_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=INVITATION_EXPIRE_DAYS),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    accept_url = f"{settings.FRONTEND_URL}/selger/godta-invitasjon?token={raw_token}"
    subject, body = build_invitation_email(current_user.seller.store_name, accept_url)
    background_tasks.add_task(EmailService().send, payload.email, subject, body)

    return {"invitation_id": invitation.id, "email": invitation.email, "expires_at": invitation.expires_at}


@router.delete("/{user_id}", dependencies=_can_manage_staff)
def remove_staff(
    user_id: int,
    current_user: User = Depends(get_current_seller_user),
    db: Session = Depends(get_db),
):
    target = (
        db.query(User)
        .filter(User.id == user_id, User.seller_id == current_user.seller_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Ansatt ikke funnet")
    if target.is_seller_owner:
        raise HTTPException(status_code=400, detail="Kan ikke fjerne butikkeieren")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Kan ikke fjerne din egen konto")

    db.delete(target)
    db.commit()
    return {"status": "removed", "id": user_id}
