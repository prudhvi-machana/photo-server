import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.auth.routes import router as auth_router
from app.api.photos import router as photos_router
from app.api.photo_head import router as photo_head_router
from app.api.albums import router as albums_router
from app.api.photos import cleanup_expired_trash
from app.db.database import Base, engine, SessionLocal
from app.db import models

Base.metadata.create_all(bind=engine)

TRASH_CLEANUP_INTERVAL = 24 * 60 * 60


async def _trash_cleanup_loop():
    while True:
        await asyncio.sleep(TRASH_CLEANUP_INTERVAL)
        db: Session = SessionLocal()
        try:
            deleted_count = cleanup_expired_trash(db)
            if deleted_count:
                print(f"Trash cleanup: permanently deleted {deleted_count} expired photo(s).")
        except Exception as exc:
            print(f"Trash cleanup failed: {exc}")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db: Session = SessionLocal()
    try:
        deleted_count = cleanup_expired_trash(db)
        if deleted_count:
            print(f"Trash cleanup: permanently deleted {deleted_count} expired photo(s).")
    finally:
        db.close()

    cleanup_task = asyncio.create_task(_trash_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Photo Server", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(photos_router)
app.include_router(photo_head_router)
app.include_router(albums_router)


@app.get("/health")
def health():
    return {"status": "ok"}
