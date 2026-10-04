from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """普通接口用：一个请求一个会话，请求结束就还给连接池。"""
    async with SessionLocal() as session:
        yield session


async def create_tables() -> None:
    # MVP 直接按模型建表；要改表结构时换成 Alembic 迁移
    from app import models  # noqa: F401  确保模型都注册到 Base 上

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
