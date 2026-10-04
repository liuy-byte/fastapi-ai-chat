import json
import os
import tempfile

# 必须在导入 app 之前设好：测试用一个临时 SQLite 文件，不碰 MySQL，也不调真模型
_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_file}"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long!!"
os.environ["LLM_FAKE"] = "true"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app import llm  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_db():
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def script(monkeypatch):
    """给这个测试指定假模型每一轮怎么回。"""

    def use(*turns: dict) -> llm.ScriptedChatModel:
        model = llm.ScriptedChatModel(turns=list(turns))
        monkeypatch.setattr(llm, "build_model", lambda: model)
        return model

    return use


async def login(client: httpx.AsyncClient, email: str) -> dict:
    cred = {"email": email, "password": "password123"}
    await client.post("/auth/register", json=cred)
    r = await client.post("/auth/login", json=cred)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 SSE 响应体拆成 (event, data) 列表，忽略保活注释。"""
    events = []
    for block in text.strip().split("\n\n"):
        name, data = "message", None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if data is not None:
            events.append((name, data))
    return events
