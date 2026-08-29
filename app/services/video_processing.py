import subprocess
from pathlib import Path

from app.db.database import SessionLocal
from app.db.models import Photo, VideoVariant
from app.storage.service import (
    generate_variant_filename,
    get_file_path,
    get_variant_path,
)

PLAYBACK_VARIANT = "1080p"


def process_video_variant(photo_id: int, user_id: int) -> None:
    """Create the playback-friendly MP4 for a video upload."""
    db = SessionLocal()
    output_path: Path | None = None

    try:
        photo = db.query(Photo).filter(
            Photo.id == photo_id,
            Photo.user_id == user_id,
        ).first()
        if photo is None:
            return

        variant = db.query(VideoVariant).filter(
            VideoVariant.photo_id == photo_id,
            VideoVariant.variant_type == PLAYBACK_VARIANT,
        ).first()
        if variant is None:
            variant = VideoVariant(
                photo_id=photo_id,
                variant_type=PLAYBACK_VARIANT,
                mime_type="video/mp4",
                status="processing",
            )
            db.add(variant)
            db.commit()
            db.refresh(variant)

        input_path = get_file_path(user_id, photo.filename)
        output_filename = variant.filename or generate_variant_filename()
        output_path = get_variant_path(user_id, output_filename)
        variant.filename = output_filename
        variant.status = "processing"
        variant.error_message = None
        db.commit()

        if not input_path.is_file():
            raise FileNotFoundError(f"Original video not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(".tmp.mp4")
        if temp_path.exists():
            temp_path.unlink()

        command = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-vf", "scale='min(1920,iw)':-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(temp_path),
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=6 * 60 * 60,
            check=False,
        )

        if result.returncode != 0 or not temp_path.is_file() or temp_path.stat().st_size == 0:
            error = result.stderr[-1000:] if result.stderr else "ffmpeg failed"
            raise RuntimeError(error)

        temp_path.replace(output_path)
        variant.file_size = output_path.stat().st_size
        variant.status = "ready"
        variant.error_message = None
        db.commit()

    except Exception as exc:
        db.rollback()
        variant = db.query(VideoVariant).filter(
            VideoVariant.photo_id == photo_id,
            VideoVariant.variant_type == PLAYBACK_VARIANT,
        ).first()
        if variant is not None:
            variant.status = "failed"
            variant.error_message = str(exc)[:1000]
            db.commit()
        if output_path is not None:
            temp_path = output_path.with_suffix(".tmp.mp4")
            if temp_path.is_file():
                temp_path.unlink()
    finally:
        db.close()
