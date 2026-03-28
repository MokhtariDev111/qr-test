from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core import get_db, hash_password, verify_password, create_token, decode_token
from app.models import User
from app.schemas import UserCreate, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2), db: AsyncSession = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")
    
    sub = payload.get("sub")
    if not sub or not str(sub).isdigit():
        raise HTTPException(401, "Invalid token subject")
        
    result = await db.execute(select(User).where(User.id == int(sub)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def require_teacher(user: User = Depends(get_current_user)):
    if user.role != "teacher":
        raise HTTPException(403, "Teachers only")
    return user


async def require_student(user: User = Depends(get_current_user)):
    if user.role != "student":
        raise HTTPException(403, "Students only")
    return user


@router.post("/register", response_model=UserResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email exists")
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        student_id=data.student_id
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_token({"sub": str(user.id), "role": user.role})
    return Token(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
