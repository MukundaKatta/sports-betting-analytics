"""FastAPI web application for Sports Betting Analytics."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sba.web.api import router as api_router
from sba.web.views import router as views_router
from sba.data.db import init_db

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SBA — Sports Betting Analytics",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router, prefix="/api")
app.include_router(views_router)


def create_app() -> FastAPI:
    return app
