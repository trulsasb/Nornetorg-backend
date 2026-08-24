from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models.invitation import StaffInvitation
from models.seller import Seller, SellerStatus
from models.user import User
from services.email_service import EmailService, build_verification_email
from utils.env import settings
from utils.tokens import hash_invitation_token

router = APIRouter(prefix="/auth", tags=["Auth"])

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * settings.JWT_EXPIRE_HOURS

# Short-lived JWT "purpose" for stateless email verification -- no DB table
# needed for this, unlike StaffInvitation (which does need server-side
# state so it can be listed/revoked before acceptance).
EMAIL_VERIFICATION_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ---------------------------------------------------------
# PASSWORD / TOKEN HELPERS
# ---------------------------------------------------------


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _create_purpose_token(purpose: str, claims: dict, expires_delta: timedelta) -> str:
    """Stateless, signed, short-lived token for a specific one-off action
    (email verification). Not a session token -- get_current_user() below
    rejects anything without a "sub" claim shaped like a real login."""
    to_encode = {**claims, "purpose": purpose, "exp": datetime.utcnow() + expires_delta}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _decode_purpose_token(token: str, purpose: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=400, detail="Ugyldig eller utløpt lenke")
    if payload.get("purpose") != purpose:
        raise HTTPException(status_code=400, detail="Ugyldig lenke")
    return payload


# ---------------------------------------------------------
# AUTH DEPENDENCIES
# ---------------------------------------------------------


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose"):
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user_id: int = payload.get("sub")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return current_user


def require_platform_permission(permission: str):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_platform_admin or getattr(current_user, permission, False):
            return current_user
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return checker


def get_current_seller_user(current_user: User = Depends(get_current_user)) -> User:
    """Any authenticated staff member of a seller (owner or invited staff).
    seller_id on the user IS the tenant boundary -- endpoints using this
    dependency must always scope queries by current_user.seller_id, never
    accept a seller_id from the request itself. See SPEC.md 4.2."""
    if current_user.seller_id is None:
        raise HTTPException(status_code=403, detail="Seller account required")
    return current_user


def require_seller_permission(permission: str):
    def checker(current_user: User = Depends(get_current_seller_user)) -> User:
        if current_user.is_seller_owner or getattr(current_user, permission, False):
            return current_user
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return checker


# ---------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------


class RegisterSellerRequest(BaseModel):
    store_name: str
    email: EmailStr
    password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str


# ---------------------------------------------------------
# REGISTER SELLER (PUBLIC) -- creates the seller + its owner user
# ---------------------------------------------------------


def _slugify(store_name: str) -> str:
    return "-".join(store_name.strip().lower().split()) or "butikk"


@router.post("/register-seller", status_code=201)
async def register_seller(
    payload: RegisterSellerRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Passordet må være minst 8 tegn")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-postadressen er allerede registrert")

    base_slug = _slugify(payload.store_name)
    slug = base_slug
    suffix = 1
    while db.query(Seller).filter(Seller.slug == slug).first():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    seller = Seller(store_name=payload.store_name, slug=slug, status=SellerStatus.PENDING_VERIFICATION)
    db.add(seller)
    db.flush()  # get seller.id before creating the owner user, same transaction

    owner = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        seller_id=seller.id,
        is_seller_owner=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(seller)

    verification_token = _create_purpose_token(
        "email_verification",
        {"seller_id": seller.id},
        timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES),
    )
    verification_url = f"{settings.FRONTEND_URL}/selger/bekreft-epost?token={verification_token}"
    subject, body = build_verification_email(seller.store_name, verification_url)
    background_tasks.add_task(EmailService().send, payload.email, subject, body)

    return {"seller_id": seller.id, "status": seller.status.value}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    payload = _decode_purpose_token(token, "email_verification")
    seller = db.query(Seller).filter(Seller.id == payload.get("seller_id")).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Selger ikke funnet")

    if seller.status == SellerStatus.PENDING_VERIFICATION:
        seller.status = SellerStatus.ACTIVE
        seller.email_verified_at = datetime.utcnow()
        db.commit()

    return {"seller_id": seller.id, "status": seller.status.value}


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_platform_admin": current_user.is_platform_admin,
        "seller_id": current_user.seller_id,
        "is_seller_owner": current_user.is_seller_owner,
        "can_edit_products": current_user.can_edit_products,
        "can_view_orders": current_user.can_view_orders,
        "can_manage_payment_methods": current_user.can_manage_payment_methods,
        "can_manage_staff": current_user.can_manage_staff,
    }


# ---------------------------------------------------------
# ACCEPT STAFF INVITATION (PUBLIC -- gated by possession of the token)
# ---------------------------------------------------------


@router.post("/accept-invitation")
async def accept_invitation(payload: AcceptInvitationRequest, db: Session = Depends(get_db)):
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Passordet må være minst 8 tegn")

    token_hash = hash_invitation_token(payload.token)
    invitation = db.query(StaffInvitation).filter(StaffInvitation.token_hash == token_hash).first()
    if not invitation:
        raise HTTPException(status_code=400, detail="Ugyldig invitasjon")
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Invitasjonen er ikke lenger gyldig")
    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitasjonen har utløpt")

    # Re-check at acceptance time, not just at invite-creation time -- the
    # email could have been registered elsewhere in the gap between the two.
    existing = db.query(User).filter(User.email == invitation.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-postadressen er allerede registrert")

    user = User(
        email=invitation.email,
        password_hash=hash_password(payload.password),
        seller_id=invitation.seller_id,
        is_seller_owner=False,
        can_edit_products=invitation.can_edit_products,
        can_view_orders=invitation.can_view_orders,
        can_manage_payment_methods=invitation.can_manage_payment_methods,
        can_manage_staff=invitation.can_manage_staff,
    )
    db.add(user)
    invitation.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id})
    return {"access_token": token, "token_type": "bearer"}
