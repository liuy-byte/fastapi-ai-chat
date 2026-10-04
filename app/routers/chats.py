import asyncio
import json
import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.agent import run_agent
from app.db import SessionLocal
from app.deps import DB, CurrentUser, OwnedChat
from app.models import Chat, Message
from app.schemas import ChatCreate, ChatDetail, ChatOut, ChatUpdate, MessageIn
from app.tools import TOOLS

log = logging.getLogger("chat")
router = APIRouter(tags=["chats"])

# 每次带给模型的历史条数上限，太长既慢又贵
HISTORY_LIMIT = 20


@router.get("/tools")
async def list_tools():
    return [{"name": t.name, "description": t.description} for t in TOOLS.values()]


@router.get("/chats", response_model=list[ChatOut])
async def list_chats(user: CurrentUser, db: DB):
    rows = await db.scalars(select(Chat).where(Chat.user_id == user.id).order_by(Chat.id.desc()))
    return rows.all()


@router.post("/chats", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, user: CurrentUser, db: DB):
    chat = Chat(user_id=user.id, **body.model_dump())
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/chats/{chat_id}", response_model=ChatDetail)
async def get_chat(chat: OwnedChat, db: DB):
    # 异步下不能靠懒加载取消息，显式一起查出来
    return await db.scalar(select(Chat).where(Chat.id == chat.id).options(selectinload(Chat.messages)))


@router.patch("/chats/{chat_id}", response_model=ChatOut)
async def rename_chat(body: ChatUpdate, chat: OwnedChat, db: DB):
    chat.title = body.title
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat: OwnedChat, db: DB):
    # 先删消息再删对话，不依赖数据库有没有开外键级联
    await db.execute(delete(Message).where(Message.chat_id == chat.id))
    await db.delete(chat)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def sse(event: str, data: dict) -> ServerSentEvent:
    # data= 会按 JSON 编码但中文转成 \uXXXX，自己编码后用 raw_data 原样发出去，抓包时能直接看懂
    return ServerSentEvent(event=event, raw_data=json.dumps(data, ensure_ascii=False))


@dataclass
class ChatContext:
    chat_id: int
    system_prompt: str
    tools: list[str]
    history: list[dict]


async def load_chat_context(chat_id: int, user: CurrentUser) -> ChatContext:
    """流式接口专用：查对话和历史用一个短会话，查完马上关，模型说多久都不占数据库连接。"""
    async with SessionLocal() as db:
        chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
        if chat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "对话不存在")
        rows = await db.scalars(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.id.desc()).limit(HISTORY_LIMIT)
        )
        history = [{"role": m.role, "content": m.content} for m in reversed(rows.all())]
        return ChatContext(chat.id, chat.system_prompt, list(chat.tools or []), history)


@router.post("/chats/{chat_id}/messages", response_class=EventSourceResponse)
async def send_message(
    body: MessageIn, ctx: Annotated[ChatContext, Depends(load_chat_context)]
) -> AsyncIterable[ServerSentEvent]:
    answer: list[str] = []
    new_round = False  # 中间调过工具，模型下一轮说的话另起一段存
    try:
        async for ev in run_agent(ctx.system_prompt, ctx.tools, ctx.history, body.content):
            if ev.type == "token":
                if new_round and answer:
                    answer.append("\n\n")
                new_round = False
                answer.append(ev.data["text"])
            else:
                new_round = True
            yield sse(ev.type, ev.data)
    except (asyncio.CancelledError, GeneratorExit) as e:
        # 客户端断开时走到这里：正在等模型时被取消是 CancelledError，停在 yield 上被关闭是 GeneratorExit。
        # 两种都只记日志、什么都不存，接着往上抛让框架收尾
        log.warning("chat %s 客户端断开（%s），已输出 %d 段，本轮不保存", ctx.chat_id, type(e).__name__, len(answer))
        raise
    except Exception:
        # 模型或工具出错：日志里留完整异常，给前端的只说出错了，不把内部信息带出去
        log.exception("chat %s 生成失败，本轮不保存", ctx.chat_id)
        yield sse("error", {"message": "生成失败，请重试"})
        return

    # 整轮成功才落库，用户消息和回答在一个事务里，要么都在要么都不在
    try:
        async with SessionLocal() as db:
            user_msg = Message(chat_id=ctx.chat_id, role="user", content=body.content)
            bot_msg = Message(chat_id=ctx.chat_id, role="assistant", content="".join(answer))
            db.add_all([user_msg, bot_msg])
            await db.commit()
    except Exception:
        log.exception("chat %s 保存失败", ctx.chat_id)
        yield sse("error", {"message": "回答已生成但保存失败，请重试"})
        return
    # done 放在提交之后发：前端收到 done，就说明这一轮已经在库里了
    yield sse("done", {"user_message_id": user_msg.id, "assistant_message_id": bot_msg.id})
