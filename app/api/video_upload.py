from pathlib import Path
import mimetypes

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Photo, User, VideoVariant
from app.storage.service import (
    generate_filename,
    generate_variant_filename,
    get_user_storage,
    get_variant_path,
    is_video_filename,
)

router = APIRouter(prefix="/photos", tags=["Photos"])
MAX_FILE_SIZE = 1024 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def infer_mime_type(filename: str, supplied: str | None) -> str:
    supplied = (supplied or "").strip().lower()
    if supplied and supplied != "application/octet-stream":
        return supplied
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


async def _save_upload(upload: UploadFile, path: Path) -> int:
    total_size = 0
    try:
        with path.open("wb") as output:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File too large. Maximum size is 1 GB.")
                output.write(chunk)
        return total_size
    except HTTPException:
        if path.is_file():
            path.unlink()
        raise
    except Exception as exc:
        if path.is_file():
            path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to store upload: {exc}")
    finally:
        await upload.close()


@router.post("/upload-video")
async def upload_video(
    original_file: UploadFile = File(...),
    playback_file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = original_file.filename or "video.mp4"
    if not is_video_filename(original_name):
        raise HTTPException(status_code=400, detail="Original file is not a supported video")

    if not (playback_file.filename or "").lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Playback file must be an MP4")

    try:
        original_filename = generate_filename(original_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    playback_filename = generate_variant_filename()
    original_path = get_user_storage(user.id) / original_filename
    playback_path = get_variant_path(user.id, playback_filename)

    try:
        original_size = await _save_upload(original_file, original_path)
        playback_size = await _save_upload(playback_file, playback_path)

        if playback_size == 0:
            raise HTTPException(status_code=400, detail="Playback file is empty")

        photo = Photo(
            user_id=user.id,
            filename=original_filename,
            original_filename=original_name,
            mime_type=infer_mime_type(original_name, original_file.content_type),
            file_size=original_size,
        )
        db.add(photo)
        db.flush()

        variant = VideoVariant(
            photo_id=photo.id,
            variant_type="1080p",
            filename=playback_filename,
            mime_type="video/mp4",
            file_size=playback_size,
            status="ready",
        )
        db.add(variant)
        db.commit()
        db.refresh(photo)

        return {
            "id": photo.id,
            "filename": photo.filename,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "size": photo.file_size,
            "uploaded_at": photo.uploaded_at,
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "playback": {
                "status": "ready",
                "url": f"/photos/{photo.id}/playback",
            },
        }
    except HTTPException:
        db.rollback()
        if original_path.is_file():
            original_path.unlink()
        if playback_path.is_file():
            playback_path.unlink()
        raise
    except Exception:
        db.rollback()
        if original_path.is_file():
            original_path.unlink()
        if playback_path.is_file():
            playback_path.unlink()
        raise HTTPException(status_code=500, detail="Failed to save video and playback copy")
