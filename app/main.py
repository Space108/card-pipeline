from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import connect
from app.core.logging import setup_logging
from app.routers import cards, jobs, workflows


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    conn = connect()  # проверка БД + применение schema.sql
    conn.close()
    yield


app = FastAPI(title="card-pipeline", lifespan=lifespan)
app.include_router(cards.router)
app.include_router(jobs.router)
app.include_router(workflows.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
