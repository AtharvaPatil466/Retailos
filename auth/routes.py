import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import create_access_token, hash_password, verify_password
from db.models import User
from db.session import get_db
from auth.dependencies import require_role

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    role: str = "staff"
    phone: str | None = None
    model_config = ConfigDict(json_schema_extra={"examples": [{"username": "rajesh_owner", "email": "rajesh@store.com", "password": "SecurePass123!", "full_name": "Rajesh Kumar", "role": "owner", "phone": "+919876543210"}]})


class LoginRequest(BaseModel):
    username: str
    password: str
    model_config = ConfigDict(json_schema_extra={"examples": [{"username": "rajesh_owner", "password": "SecurePass123!"}]})


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    model_config = ConfigDict(json_schema_extra={"examples": [{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer", "user": {"id": "usr_abc123", "username": "rajesh_owner", "email": "rajesh@store.com", "full_name": "Rajesh Kumar", "role": "owner"}}]})


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: str
    phone: str | None
    is_active: bool
    model_config = ConfigDict(json_schema_extra={"examples": [{"id": "usr_abc123", "username": "rajesh_owner", "email": "rajesh@store.com", "full_name": "Rajesh Kumar", "role": "owner", "phone": "+919876543210", "is_active": True}]})


@router.post("/register", response_model=TokenResponse, summary="Register a new user", responses={400: {"description": "Username/email taken or invalid role"}})
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already registered")

    if body.role not in ("owner", "manager", "staff", "cashier"):
        raise HTTPException(status_code=400, detail="Invalid role")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        phone=body.phone,
        store_id="store-001",
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": user.id, "role": user.role, "store_id": user.store_id})

    return TokenResponse(
        access_token=token,
        user={"id": user.id, "username": user.username, "email": user.email, "full_name": user.full_name, "role": user.role},
    )


@router.post("/login", response_model=TokenResponse, summary="Login with credentials", responses={401: {"description": "Invalid credentials"}, 403: {"description": "Account deactivated"}})
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    user.last_login = time.time()
    await db.flush()

    token = create_access_token({"sub": user.id, "role": user.role, "store_id": user.store_id})

    return TokenResponse(
        access_token=token,
        user={"id": user.id, "username": user.username, "email": user.email, "full_name": user.full_name, "role": user.role},
    )


@router.get("/me", response_model=UserResponse, summary="Get current user profile", responses={401: {"description": "Not authenticated"}})
async def get_me(user: User = Depends(require_role("cashier"))):
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        phone=user.phone,
        is_active=user.is_active,
    )


@router.get("/users", response_model=list[UserResponse], summary="List all users (owner only)", responses={403: {"description": "Insufficient role"}})
async def list_users(
    user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.store_id == user.store_id).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        UserResponse(id=u.id, username=u.username, email=u.email, full_name=u.full_name, role=u.role, phone=u.phone, is_active=u.is_active)
        for u in users
    ]


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str,
    current_user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    if role not in ("owner", "manager", "staff", "cashier"):
        raise HTTPException(status_code=400, detail="Invalid role")

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.role = role
    await db.flush()
    return {"status": "ok", "user_id": user_id, "new_role": role}


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    target_user.is_active = False
    await db.flush()
    return {"status": "ok", "user_id": user_id, "is_active": False}
