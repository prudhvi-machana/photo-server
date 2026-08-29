from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.db.database import get_db
from app.db.models import User
from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.auth.password import verify_password
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register")
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter(User.username == data.username)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username,
    }


@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.username == data.username)
        .first()
    )

    if not user or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.post("/refresh")
def refresh(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    try:
        user_id = decode_refresh_token(data.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": data.refresh_token,
        "token_type": "bearer",
    }


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
    }
