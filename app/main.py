import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import create_tables
from app.routers import auth, chats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="FastAPI AI Chat MVP", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(chats.router)


@app.get("/health")
async def health():
    return {"ok": True}
