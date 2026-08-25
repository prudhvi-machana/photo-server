from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
import mimetypes
import subprocess

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from PIL import Image

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Photo, User
from app.storage.service import (
    generate_filename,
    get_stream_path,
    get_thumbnail_path,
    get_user_storage,
    is_video_filename,
    supports_faststart_remux,
)

router = APIRouter(prefix="/photos", tags=["Photos"])

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB
STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MB


def infer_mime_type(filename: str, supplied: str | None) -> str:
    supplied = (supplied or "").strip().lower()
    if supplied and supplied != "application/octet-stream":
        return supplied

    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def generate_video_thumbnail(video_path: Path, thumbnail_path: Path) -> bool:
    """Generate one JPEG frame using ffmpeg. Failure does not fail the upload."""
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    if thumbnail_path.is_file() and thumbnail_path.stat().st_size > 0:
        return True

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0.5",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=400:-2",
                "-q:v",
                "4",
                str(thumbnail_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return result.returncode == 0 and thumbnail_path.is_file()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def generate_video_stream(video_path: Path, stream_path: Path) -> bool:
    """Create a playback copy with the MP4 moov atom at the beginning.

    This is a remux only: audio/video are copied without re-encoding, so the
    original quality is preserved. The original file remains untouched.
    """
    stream_path.parent.mkdir(parents=True, exist_ok=True)

    if stream_path.is_file() and stream_path.stat().st_size > 0:
        return True

    temp_path = stream_path.with_suffix(stream_path.suffix + ".tmp")

    try:
        if temp_path.is_file():
            temp_path.unlink()

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-map",
                "0",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temp_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )

        if result.returncode != 0 or not temp_path.is_file() or temp_path.stat().st_size == 0:
            if temp_path.is_file():
                temp_path.unlink()
            return False

        temp_path.replace(stream_path)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        if temp_path.is_file():
            temp_path.unlink()
        return False


def generate_image_thumbnail(image_path: Path, thumbnail_path: Path) -> bool:
    try:
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(image_path)
        image.thumbnail((400, 400))
        output = BytesIO()

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        image.save(output, format="JPEG", quality=80)
        thumbnail_path.write_bytes(output.getvalue())
        return True
    except Exception:
        return False


def ensure_thumbnail(photo: Photo, user_id: int) -> Path | None:
    file_path = get_user_storage(user_id) / photo.filename
    thumbnail_path = get_thumbnail_path(user_id, photo.filename)

    if not file_path.is_file():
        return None

    if thumbnail_path.is_file() and thumbnail_path.stat().st_size > 0:
        return thumbnail_path

    if is_video_filename(photo.filename):
        return thumbnail_path if generate_video_thumbnail(file_path, thumbnail_path) else None

    return thumbnail_path if generate_image_thumbnail(file_path, thumbnail_path) else None


def ensure_stream_file(photo: Photo, user_id: int) -> Path | None:
    """Return an optimized playback file for formats that support faststart."""
    if not is_video_filename(photo.filename) or not supports_faststart_remux(photo.filename):
        return get_user_storage(user_id) / photo.filename

    source_path = get_user_storage(user_id) / photo.filename
    stream_path = get_stream_path(user_id, photo.filename)

    if not source_path.is_file():
        return None

    if generate_video_stream(source_path, stream_path):
        return stream_path

    # Playback can still fall back to the original if remuxing fails.
    return source_path


def media_item(photo: Photo) -> dict:
    # Older uploads may have been stored as application/octet-stream. Return
    # the MIME type inferred from the filename so clients can still identify
    # and play those videos correctly without a database migration.
    effective_mime = infer_mime_type(photo.original_filename, photo.mime_type)
    return {
        "id": photo.id,
        "filename": photo.filename,
        "original_filename": photo.original_filename,
        "mime_type": effective_mime,
        "size": photo.file_size,
        "uploaded_at": photo.uploaded_at,
        "thumbnail_url": f"/photos/{photo.id}/thumbnail",
    }


@router.get("")
def list_photos(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photos = (
        db.query(Photo)
        .filter(Photo.user_id == user.id, Photo.deleted_at.is_(None))
        .order_by(Photo.uploaded_at.desc())
        .all()
    )
    return [media_item(photo) for photo in photos]


@router.get("/recent")
def list_recent_photos(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photos = (
        db.query(Photo)
        .filter(Photo.user_id == user.id, Photo.deleted_at.is_(None))
        .order_by(Photo.uploaded_at.desc())
        .limit(50)
        .all()
    )
    return [media_item(photo) for photo in photos]


@router.get("/{photo_id}/thumbnail")
def get_photo_thumbnail(
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.user_id == user.id)
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    thumbnail_path = ensure_thumbnail(photo, user.id)
    if thumbnail_path is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to generate media thumbnail. Install ffmpeg for video thumbnails.",
        )

    return FileResponse(path=thumbnail_path, media_type="image/jpeg")


@router.get("/trash")
def list_trash(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photos = (
        db.query(Photo)
        .filter(Photo.user_id == user.id, Photo.deleted_at.isnot(None))
        .order_by(Photo.deleted_at.desc())
        .all()
    )

    return [
        {
            **media_item(photo),
            "deleted_at": photo.deleted_at,
            "days_remaining": max(
                0,
                30 - (datetime.utcnow() - photo.deleted_at).days,
            ),
        }
        for photo in photos
    ]


@router.get("/{photo_id}")
async def get_photo(
    photo_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.user_id == user.id,
            Photo.deleted_at.is_(None),
        )
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    if not is_video_filename(photo.filename):
        file_path = get_user_storage(user.id) / photo.filename
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Photo file not found")
        return FileResponse(
            path=file_path,
            media_type=infer_mime_type(photo.original_filename, photo.mime_type),
            filename=photo.original_filename,
        )

    file_path = ensure_stream_file(photo, user.id)
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    media_type = "video/mp4" if file_path.suffix.lower() == ".mp4" else infer_mime_type(photo.original_filename, photo.mime_type)

    if not range_header:
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": f'inline; filename="{photo.original_filename}"',
        }
        return StreamingResponse(
            _file_iterator(file_path, 0, file_size - 1),
            status_code=200,
            media_type=media_type,
            headers=headers,
        )

    if not range_header.startswith("bytes="):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    try:
        range_value = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
        start_text, end_text = range_value.split("-", 1)

        if start_text == "":
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
            if start < 0 or start >= file_size:
                raise ValueError
            end = min(end, file_size - 1)
            if end < start:
                raise ValueError
    except (ValueError, TypeError):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    content_length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Disposition": f'inline; filename="{photo.original_filename}"',
    }

    return StreamingResponse(
        _file_iterator(file_path, start, end),
        status_code=206,
        media_type=media_type,
        headers=headers,
    )


def _file_iterator(path: Path, start: int, end: int):
    with path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.post("/trash/{photo_id}/restore")
def restore_photo(
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.user_id == user.id,
            Photo.deleted_at.isnot(None),
        )
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found in trash")

    photo.deleted_at = None
    db.commit()
    db.refresh(photo)
    return {"message": "Photo restored successfully", "id": photo.id}


@router.delete("/trash/{photo_id}")
def permanently_delete_photo(
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.user_id == user.id,
            Photo.deleted_at.isnot(None),
        )
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found in trash")

    file_path = get_user_storage(user.id) / photo.filename
    thumbnail_path = get_thumbnail_path(user.id, photo.filename)
    stream_path = get_stream_path(user.id, photo.filename)

    if file_path.is_file():
        file_path.unlink()
    if thumbnail_path.is_file():
        thumbnail_path.unlink()
    if stream_path.is_file():
        stream_path.unlink()

    db.delete(photo)
    db.commit()
    return {"message": "Photo permanently deleted", "id": photo_id}


@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        filename = generate_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    storage_dir = get_user_storage(user.id)
    file_path = storage_dir / filename
    total_size = 0

    try:
        with file_path.open("wb") as output:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File too large. Maximum size is 1 GB.",
                    )

                output.write(chunk)
    except HTTPException:
        if file_path.is_file():
            file_path.unlink()
        raise
    except Exception:
        if file_path.is_file():
            file_path.unlink()
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")
    finally:
        await file.close()

    photo = Photo(
        user_id=user.id,
        filename=filename,
        original_filename=file.filename or filename,
        mime_type=infer_mime_type(file.filename or filename, file.content_type),
        file_size=total_size,
    )

    db.add(photo)
    db.commit()
    db.refresh(photo)

    ensure_thumbnail(photo, user.id)
    if is_video_filename(photo.filename) and supports_faststart_remux(photo.filename):
        ensure_stream_file(photo, user.id)

    return media_item(photo)


@router.delete("/{photo_id}")
def delete_photo(
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.user_id == user.id,
            Photo.deleted_at.is_(None),
        )
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.deleted_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Photo moved to trash",
        "id": photo_id,
        "deleted_at": photo.deleted_at,
    }


def cleanup_expired_trash(db: Session):
    cutoff = datetime.utcnow() - timedelta(days=30)

    photos = (
        db.query(Photo)
        .filter(
            Photo.deleted_at.isnot(None),
            Photo.deleted_at <= cutoff,
        )
        .all()
    )

    deleted_count = 0

    for photo in photos:
        file_path = get_user_storage(photo.user_id) / photo.filename
        thumbnail_path = get_thumbnail_path(photo.user_id, photo.filename)
        stream_path = get_stream_path(photo.user_id, photo.filename)

        if file_path.is_file():
            file_path.unlink()
        if thumbnail_path.is_file():
            thumbnail_path.unlink()
        if stream_path.is_file():
            stream_path.unlink()

        db.delete(photo)
        deleted_count += 1

    db.commit()
    return deleted_count
