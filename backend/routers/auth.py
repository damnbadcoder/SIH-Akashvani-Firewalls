import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.schemas.auth import UserRegister, UserLogin, UserSync, UserOut

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

@router.post("/register", response_model=UserOut)
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered."
        )
    
    new_user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=_hash(payload.password),
        user_type=payload.user_type,
        organisation=payload.organisation,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=UserOut)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or user.hashed_password != _hash(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    return user

@router.post("/sync", response_model=UserOut)
def sync_firebase_user(payload: UserSync, db: Session = Depends(get_db)):
    """
    Sync or upsert an authenticated Firebase / Google OAuth user into backend DB.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        user = User(
            name=payload.name,
            email=payload.email,
            user_type=payload.user_type,
            organisation=payload.organisation,
        )
        db.add(user)
    else:
        if payload.name:
            user.name = payload.name
        if payload.organisation is not None:
            user.organisation = payload.organisation
        if payload.user_type:
            user.user_type = payload.user_type
    db.commit()
    db.refresh(user)
    return user

