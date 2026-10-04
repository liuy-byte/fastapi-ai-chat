from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Message
from tests.conftest import login, parse_sse


async def test_cannot_touch_other_users_chat(client, script):
    alice = await login(client, "alice@example.com")
    bob = await login(client, "bob@example.com")
    chat_id = (await client.post("/chats", json={"title": "alice 的对话"}, headers=alice)).json()["id"]

    # bob 拿着 alice 的对话 id，查、改、删、发消息都当它不存在
    assert (await client.get(f"/chats/{chat_id}", headers=bob)).status_code == 404
    assert (await client.patch(f"/chats/{chat_id}", json={"title": "x"}, headers=bob)).status_code == 404
    assert (await client.delete(f"/chats/{chat_id}", headers=bob)).status_code == 404
    r = await client.post(f"/chats/{chat_id}/messages", json={"content": "hi"}, headers=bob)
    assert r.status_code == 404
    assert (await client.get("/chats", headers=bob)).json() == []

    # alice 自己的还在
    assert (await client.get(f"/chats/{chat_id}", headers=alice)).json()["title"] == "alice 的对话"


async def test_unknown_tool_rejected(client):
    alice = await login(client, "alice@example.com")
    r = await client.post("/chats", json={"tools": ["calculator", "rm_rf"]}, headers=alice)
    assert r.status_code == 422


async def test_stream_with_tool_call_then_saved(client, script):
    script(
        {"text": "我算一下。", "tool_calls": [{"name": "calculator", "args": {"expression": "1200*0.85/3"}}]},
        {"text": "每人 340 元。"},
    )
    alice = await login(client, "alice@example.com")
    chat_id = (await client.post("/chats", json={"tools": ["calculator"]}, headers=alice)).json()["id"]

    r = await client.post(f"/chats/{chat_id}/messages", json={"content": "1200 打 85 折三人分"}, headers=alice)
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [e for e, _ in events]

    assert names[0] == "token"
    assert names.index("tool_call") < names.index("tool_result") < names.index("done")
    assert names[-1] == "done"
    tool_result = next(d for e, d in events if e == "tool_result")
    assert tool_result["content"] == "340.0"

    msgs = (await client.get(f"/chats/{chat_id}", headers=alice)).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    # 调工具前后两段话之间空一行存
    assert msgs[1]["content"] == "我算一下。\n\n每人 340 元。"


async def test_model_error_midway_saves_nothing(client, script):
    script({"text": "这句话说到一半", "fail_after": 3})
    alice = await login(client, "alice@example.com")
    chat_id = (await client.post("/chats", json={}, headers=alice)).json()["id"]

    r = await client.post(f"/chats/{chat_id}/messages", json={"content": "你好"}, headers=alice)
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names == ["token", "token", "token", "error"]
    # 错误信息不带内部异常
    assert events[-1][1] == {"message": "生成失败，请重试"}

    msgs = (await client.get(f"/chats/{chat_id}", headers=alice)).json()["messages"]
    assert msgs == []


async def test_history_is_sent_to_model(client, script):
    model = script({"text": "第一轮回答"}, {"text": "第二轮回答"})
    alice = await login(client, "alice@example.com")
    chat_id = (await client.post("/chats", json={}, headers=alice)).json()["id"]

    await client.post(f"/chats/{chat_id}/messages", json={"content": "第一问"}, headers=alice)
    await client.post(f"/chats/{chat_id}/messages", json={"content": "第二问"}, headers=alice)

    seen = [m.content for m in model.seen[-1] if m.type in ("human", "ai")]
    assert seen == ["第一问", "第一轮回答", "第二问"]
    msgs = (await client.get(f"/chats/{chat_id}", headers=alice)).json()["messages"]
    assert len(msgs) == 4


async def test_delete_chat_removes_messages(client, script):
    script({"text": "好"})
    alice = await login(client, "alice@example.com")
    chat_id = (await client.post("/chats", json={}, headers=alice)).json()["id"]
    await client.post(f"/chats/{chat_id}/messages", json={"content": "hi"}, headers=alice)

    assert (await client.delete(f"/chats/{chat_id}", headers=alice)).status_code == 204
    assert (await client.get(f"/chats/{chat_id}", headers=alice)).status_code == 404
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Message)) == 0
