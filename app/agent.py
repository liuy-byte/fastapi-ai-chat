"""把一次对话交给 agent 跑，翻译成前端好处理的几种事件。这里不碰数据库。"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app import llm
from app.tools import TOOLS


@dataclass
class Event:
    type: str  # token / tool_call / tool_result
    data: dict


async def run_agent(
    system_prompt: str, tool_names: list[str], history: list[dict], user_text: str
) -> AsyncIterator[Event]:
    agent = create_agent(
        llm.build_model(),
        [TOOLS[n] for n in tool_names if n in TOOLS],
        system_prompt=system_prompt or "你是一个简洁、准确的中文助手。",
    )
    messages = [*history, {"role": "user", "content": user_text}]

    # messages 模式拿逐字输出，updates 模式拿完整的工具调用和工具结果
    async for mode, data in agent.astream({"messages": messages}, stream_mode=["messages", "updates"]):
        if mode == "messages":
            chunk, _meta = data
            if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                yield Event("token", {"text": chunk.content})
            continue
        for node, update in data.items():
            for msg in (update or {}).get("messages", []):
                if node == "model" and isinstance(msg, AIMessage):
                    for tc in msg.tool_calls:
                        yield Event("tool_call", {"id": tc["id"], "name": tc["name"], "args": tc["args"]})
                elif isinstance(msg, ToolMessage):
                    yield Event("tool_result", {"id": msg.tool_call_id, "name": msg.name, "content": str(msg.content)})
