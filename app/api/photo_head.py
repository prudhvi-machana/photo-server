from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Photo, User
from app.storage.service import get_user_storage, is_video_filename
from app.api.photos import ensure_stream_file, infer_mime_type

router = APIRouter(prefix="/photos", tags=["Photos"])


@router.head("/{photo_id}")
def head_photo(
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

    if is_video_filename(photo.filename):
        file_path = ensure_stream_file(photo, user.id)
        if file_path is None or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Video file not found")
        media_type = "video/mp4" if file_path.suffix.lower() == ".mp4" else infer_mime_type(photo.original_filename, photo.mime_type)
    else:
        file_path = get_user_storage(user.id) / photo.filename
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Photo file not found")
        media_type = infer_mime_type(photo.original_filename, photo.mime_type)

    return Response(
        status_code=200,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes" if is_video_filename(photo.filename) else "none",
            "Content-Length": str(file_path.stat().st_size),
            "Content-Disposition": f'inline; filename="{photo.original_filename}"',
        },
    )
