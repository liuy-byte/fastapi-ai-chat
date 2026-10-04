# fastapi-ai-chat

用 FastAPI 做的 AI 对话后端 MVP：注册登录、每个人只能看自己的对话、模型可以调本地工具、回答用 SSE 一个字一个字推给前端，出错或断开不留半条记录。

公众号「技术洋」文章《FastAPI 做 AI 对话后端 MVP》的配套代码。

## 技术栈

- FastAPI（原生 SSE：`EventSourceResponse` + `ServerSentEvent`）
- SQLAlchemy 2 异步 + MySQL 8.4（aiomysql）
- PyJWT + pwdlib（Argon2）
- LangChain 1.x `create_agent`，模型走 OpenAI 兼容接口
- pytest + httpx，测试用 SQLite 和脚本化假模型，不联网

## 跑起来

```bash
uv sync
docker compose up -d --wait        # 起 MySQL
cp .env.example .env               # 填 JWT_SECRET 和 LLM_API_KEY；没有 key 就把 LLM_FAKE 设成 true
uv run uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 可以直接点着试。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/register | 注册 |
| POST | /auth/login | 登录，返回 access_token |
| GET | /auth/me | 当前用户 |
| GET | /tools | 可用工具 |
| GET | /chats | 我的对话列表 |
| POST | /chats | 新建对话，可指定 system_prompt 和 tools |
| GET | /chats/{id} | 对话详情和消息 |
| PATCH | /chats/{id} | 改标题 |
| DELETE | /chats/{id} | 删除对话和消息 |
| POST | /chats/{id}/messages | 发消息，SSE 流式返回 |

SSE 事件：`token`（一段文字）、`tool_call`（模型要调工具）、`tool_result`（工具结果）、`done`（这一轮已保存）、`error`（出错，这一轮没保存）。

```bash
curl -N -X POST http://127.0.0.1:8000/chats/1/messages \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"今天几号？"}'
```

## 测试

```bash
uv run pytest
```

## 目录

```
app/
  config.py      配置，全部从环境变量读
  db.py          引擎、会话、建表
  models.py      users / chats / messages
  schemas.py     请求和响应的数据结构
  security.py    密码哈希、签发和校验 JWT
  deps.py        当前用户、按归属查对话
  tools.py       模型可调用的工具
  llm.py         真实模型和假模型
  agent.py       跑 agent，翻译成事件
  routers/       auth 和 chats 两组接口
  main.py        组装应用
tests/
```

## 没做的

刷新令牌、限流、对话标题自动生成、工具调用过程入库、多实例部署时的会话粘连。这些都是上线前要补的，MVP 先不做。
