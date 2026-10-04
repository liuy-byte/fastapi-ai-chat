from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser
from app.models import User
from app.schemas import Credentials, Token, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: Credentials, db: DB):
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 靠唯一索引兜底，两个人同时注册同一个邮箱也只会成功一个
        raise HTTPException(status.HTTP_409_CONFLICT, "邮箱已注册")
    return user


@router.post("/login", response_model=Token)
async def login(body: Credentials, db: DB):
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    # 邮箱不存在和密码错返回同一句话，不让人拿登录接口试探哪些邮箱注册过
    if not verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "邮箱或密码错误")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
