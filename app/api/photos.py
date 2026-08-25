from io import BytesIO
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from PIL import Image

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Photo, User
from app.storage.service import generate_filename, get_user_storage, is_video_filename

router = APIRouter(prefix="/photos", tags=["Photos"])

# Large media must be streamed to disk instead of loaded into RAM.
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


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

    return [
        {
            "id": photo.id,
            "filename": photo.filename,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "size": photo.file_size,
            "uploaded_at": photo.uploaded_at,
        }
        for photo in photos
    ]


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

    return [
        {
            "id": photo.id,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "size": photo.file_size,
            "uploaded_at": photo.uploaded_at,
            "thumbnail_url": (
                None
                if is_video_filename(photo.filename)
                else f"/photos/{photo.id}/thumbnail"
            ),
        }
        for photo in photos
    ]


@router.get("/{photo_id}/thumbnail")
def get_photo_thumbnail(
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Thumbnails are also needed by the Trash screen, so deliberately do not
    # filter on deleted_at here. Authorization is still enforced by user_id.
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.user_id == user.id)
        .first()
    )

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    if is_video_filename(photo.filename):
        raise HTTPException(
            status_code=415,
            detail="Video thumbnails are not generated yet",
        )

    file_path = get_user_storage(user.id) / photo.filename

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file not found")

    try:
        image = Image.open(file_path)
        image.thumbnail((400, 400))
        output = BytesIO()

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        image.save(output, format="JPEG", quality=80)
        output.seek(0)
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to generate thumbnail")

    return StreamingResponse(output, media_type="image/jpeg")


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
            "id": photo.id,
            "filename": photo.filename,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "size": photo.file_size,
            "uploaded_at": photo.uploaded_at,
            "deleted_at": photo.deleted_at,
            "days_remaining": max(
                0,
                30 - (datetime.utcnow() - photo.deleted_at).days,
            ),
            "thumbnail_url": (
                None
                if is_video_filename(photo.filename)
                else f"/photos/{photo.id}/thumbnail"
            ),
        }
        for photo in photos
    ]


@router.get("/{photo_id}")
def get_photo(
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

    file_path = get_user_storage(user.id) / photo.filename

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file not found")

    return FileResponse(
        path=file_path,
        media_type=photo.mime_type,
        filename=photo.original_filename,
    )


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
    if file_path.is_file():
        file_path.unlink()

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
        mime_type=file.content_type or "application/octet-stream",
        file_size=total_size,
    )

    db.add(photo)
    db.commit()
    db.refresh(photo)

    return {
        "id": photo.id,
        "filename": photo.filename,
        "original_filename": photo.original_filename,
        "mime_type": photo.mime_type,
        "size": photo.file_size,
    }


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

        if file_path.is_file():
            file_path.unlink()

        db.delete(photo)
        deleted_count += 1

    db.commit()
    return deleted_count
