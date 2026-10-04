from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_db
from app.models import Chat, User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

DB = Annotated[AsyncSession, Depends(get_db)]


def _unauthorized(detail: str = "登录已失效，请重新登录") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if cred is None:
        raise _unauthorized("请先登录")
    user_id = decode_access_token(cred.credentials)
    if user_id is None:
        raise _unauthorized()
    # 自己开一个短会话查完就关，流式接口也能放心用，不会把连接一直占到流结束
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_owned_chat(chat_id: int, user: CurrentUser, db: DB) -> Chat:
    """按 id 和当前用户一起查。别人的对话和不存在的对话一样返回 404，不暴露它存在。"""
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "对话不存在")
    return chat


OwnedChat = Annotated[Chat, Depends(get_owned_chat)]
