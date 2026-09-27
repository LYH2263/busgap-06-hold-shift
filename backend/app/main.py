from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


def _ensure_schema():
    """轻量迁移：为已存在的 lines 表补充新增列（create_all 不会改已有表）。"""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "lines" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("lines")}
        with engine.begin() as conn:
            if "max_hold_min" not in cols:
                conn.execute(text("ALTER TABLE lines ADD COLUMN max_hold_min FLOAT DEFAULT 5.0"))


app = FastAPI(title="BusGap", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
