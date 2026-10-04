from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.tools import TOOLS


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


class ChatCreate(BaseModel):
    title: str = Field(default="新对话", max_length=100)
    system_prompt: str = Field(default="", max_length=4000)
    tools: list[str] = []

    @field_validator("tools")
    @classmethod
    def tools_must_exist(cls, v: list[str]) -> list[str]:
        # 建对话时就把写错的工具名挡掉，别等到模型调用时才报错
        unknown = set(v) - TOOLS.keys()
        if unknown:
            raise ValueError(f"没有这些工具：{', '.join(sorted(unknown))}")
        return v


class ChatUpdate(BaseModel):
    title: str = Field(max_length=100)


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    system_prompt: str
    tools: list[str]
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    created_at: datetime


class ChatDetail(ChatOut):
    messages: list[MessageOut]


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
