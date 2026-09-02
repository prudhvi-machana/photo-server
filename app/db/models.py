from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
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

    favorites: Mapped[list["Favorite"]] = relationship(
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

    video_variants: Mapped[list["VideoVariant"]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
    )

    favorite_entries: Mapped[list["Favorite"]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
    )


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="favorites",
    )

    photo: Mapped["Photo"] = relationship(
        back_populates="favorite_entries",
    )


class VideoVariant(Base):
    __tablename__ = "video_variants"
    __table_args__ = (
        UniqueConstraint("photo_id", "variant_type", name="uq_video_variant_photo_type"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    variant_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="video/mp4",
    )

    file_size: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
    )

    error_message: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
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

    photo: Mapped["Photo"] = relationship(
        back_populates="video_variants",
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
