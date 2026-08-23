from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    albums: Mapped[list["Album"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        nullable=False,
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="photos",
    )

    album_photos: Mapped[list["AlbumPhoto"]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
    )


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="albums",
    )

    album_photos: Mapped[list["AlbumPhoto"]] = relationship(
        back_populates="album",
        cascade="all, delete-orphan",
    )


class AlbumPhoto(Base):
    __tablename__ = "album_photos"

    album_id: Mapped[int] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"),
        primary_key=True,
    )

    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    album: Mapped["Album"] = relationship(
        back_populates="album_photos",
    )

    photo: Mapped["Photo"] = relationship(
        back_populates="album_photos",
    )