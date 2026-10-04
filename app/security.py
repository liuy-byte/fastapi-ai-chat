from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import settings

# 默认用 Argon2 算哈希，验证时也认得出旧格式
password_hash = PasswordHash.recommended()


def hash_password(raw: str) -> str:
    return password_hash.hash(raw)


def verify_password(raw: str, hashed: str | None) -> bool:
    # 用户不存在时也算一次哈希，响应时间和密码错时差不多，别人没法靠快慢猜邮箱
    return password_hash.verify(raw, hashed or _DUMMY_HASH) and hashed is not None


_DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    """验签、查过期都交给 PyJWT；算法写死，不信令牌头部自己写的 alg。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError:
        return None
    return int(payload["sub"])
