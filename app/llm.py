"""模型从这里拿。真实模型走 OpenAI 兼容接口；假模型按脚本吐字，测试和断线演示用。"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from app.config import settings


class ScriptedChatModel(BaseChatModel):
    """按脚本回复的假模型。

    turns 里每一项是模型的一轮回复：
      {"text": "要输出的字", "tool_calls": [{"name": ..., "args": {...}}], "fail_after": 3}
    fail_after 表示输出几个字之后抛异常，用来模拟模型中途出错。
    没给 turns 时，原样复述用户最后一句话，每个字之间停 delay 秒。
    """

    turns: list[dict] = []
    delay: float = 0.0
    calls: int = 0
    seen: list[list[BaseMessage]] = []  # 每一轮收到的完整消息，测试里用来检查历史有没有带上

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        # 假模型不需要知道工具长什么样，脚本里写了调哪个就调哪个
        return self

    def _next_turn(self, messages: list[BaseMessage]) -> dict:
        self.seen.append(list(messages))
        if not self.turns:
            last = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
            return {"text": f"收到：{last.content}"}
        turn = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        return turn

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        turn = self._next_turn(messages)
        if "fail_after" in turn:
            raise RuntimeError("模型服务出错（脚本模拟）")
        msg = AIMessage(content=turn.get("text", ""), tool_calls=_tool_calls(turn))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _astream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        turn = self._next_turn(messages)
        for i, ch in enumerate(turn.get("text", "")):
            if turn.get("fail_after") == i:
                raise RuntimeError("模型服务出错（脚本模拟）")
            if self.delay:
                await asyncio.sleep(self.delay)
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=ch))
            if run_manager:
                await run_manager.on_llm_new_token(ch, chunk=chunk)
            yield chunk
        for i, tc in enumerate(_tool_calls(turn)):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i}],
                )
            )


def _tool_calls(turn: dict) -> list[dict]:
    return [
        {"name": tc["name"], "args": tc["args"], "id": f"call_{i}", "type": "tool_call"}
        for i, tc in enumerate(turn.get("tool_calls", []))
    ]


def build_model() -> BaseChatModel:
    if settings.llm_fake:
        return ScriptedChatModel(delay=0.3)
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        streaming=True,
        timeout=60,
        max_retries=1,
        # MiniMax 默认把思考过程用 <think> 标签混在正文里，打开这个开关后思考单独返回，正文只剩回答。
        # 这是 MiniMax 自己的参数，别家接口不认，只在连 MiniMax 时带上
        extra_body={"reasoning_split": True} if "minimax" in settings.llm_base_url else None,
    )
