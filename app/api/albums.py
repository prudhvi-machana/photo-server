from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Album, AlbumPhoto, Favorite, Photo, User
from app.storage.service import is_video_filename

router = APIRouter(prefix="/albums", tags=["Albums"])


class AlbumCreate(BaseModel):
    name: str


class AlbumUpdate(BaseModel):
    name: str


@router.post("")
def create_album(data: AlbumCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Album name cannot be empty")
    album = Album(user_id=user.id, name=name)
    db.add(album)
    db.commit()
    db.refresh(album)
    return {"id": album.id, "name": album.name, "created_at": album.created_at, "updated_at": album.updated_at}


@router.get("")
def list_albums(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    albums = db.query(Album).filter(Album.user_id == user.id).order_by(Album.created_at.desc()).all()
    result = []

    for album in albums:
        photo = (
            db.query(Photo)
            .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .filter(
                AlbumPhoto.album_id == album.id,
                Photo.user_id == user.id,
                Photo.deleted_at.is_(None),
            )
            .order_by(Photo.uploaded_at.desc())
            .first()
        )

        photo_count = (
            db.query(AlbumPhoto)
            .join(Photo, Photo.id == AlbumPhoto.photo_id)
            .filter(AlbumPhoto.album_id == album.id, Photo.deleted_at.is_(None))
            .count()
        )

        thumbnail_url = None
        if photo is not None and not is_video_filename(photo.filename):
            thumbnail_url = f"/photos/{photo.id}/thumbnail"

        result.append({
            "id": album.id,
            "name": album.name,
            "photo_count": photo_count,
            "thumbnail_url": thumbnail_url,
            "created_at": album.created_at,
            "updated_at": album.updated_at,
        })

    return result


@router.get("/{album_id}")
def get_album(album_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    photo_count = (
        db.query(AlbumPhoto)
        .join(Photo, Photo.id == AlbumPhoto.photo_id)
        .filter(AlbumPhoto.album_id == album.id, Photo.deleted_at.is_(None))
        .count()
    )

    return {
        "id": album.id,
        "name": album.name,
        "photo_count": photo_count,
        "created_at": album.created_at,
        "updated_at": album.updated_at,
    }


@router.patch("/{album_id}")
def update_album(album_id: int, data: AlbumUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Album name cannot be empty")
    album.name = name
    db.commit()
    db.refresh(album)
    return {"id": album.id, "name": album.name, "created_at": album.created_at, "updated_at": album.updated_at}


@router.delete("/{album_id}")
def delete_album(album_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    db.delete(album)
    db.commit()
    return {"message": "Album deleted successfully", "id": album_id}


@router.get("/{album_id}/photos")
def list_album_photos(album_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    photos = (
        db.query(Photo)
        .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
        .filter(
            AlbumPhoto.album_id == album.id,
            Photo.user_id == user.id,
            Photo.deleted_at.is_(None),
        )
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
            "thumbnail_url": None if is_video_filename(photo.filename) else f"/photos/{photo.id}/thumbnail",
            "is_favorite": db.query(Favorite).filter(
                Favorite.user_id == user.id,
                Favorite.photo_id == photo.id,
            ).first() is not None,
        }
        for photo in photos
    ]


@router.post("/{album_id}/photos/{photo_id}")
def add_photo_to_album(album_id: int, photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.user_id == user.id, Photo.deleted_at.is_(None))
        .first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    existing = db.query(AlbumPhoto).filter(
        AlbumPhoto.album_id == album_id,
        AlbumPhoto.photo_id == photo_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Photo already belongs to this album")

    db.add(AlbumPhoto(album_id=album_id, photo_id=photo_id))
    db.commit()
    return {"message": "Photo added to album", "album_id": album_id, "photo_id": photo_id}


@router.delete("/{album_id}/photos/{photo_id}")
def remove_photo_from_album(album_id: int, photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id, Album.user_id == user.id).first()
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    album_photo = db.query(AlbumPhoto).filter(
        AlbumPhoto.album_id == album_id,
        AlbumPhoto.photo_id == photo_id,
    ).first()
    if album_photo is None:
        raise HTTPException(status_code=404, detail="Photo is not in this album")

    db.delete(album_photo)
    db.commit()
    return {"message": "Photo removed from album", "album_id": album_id, "photo_id": photo_id}
