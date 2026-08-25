from pathlib import Path
from uuid import uuid4

BASE_STORAGE = Path("storage/users")

ALLOWED_EXTENSIONS = {
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    # Videos
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".3gp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".3gp",
}


def get_user_storage(user_id: int) -> Path:
    user_dir = BASE_STORAGE / str(user_id) / "originals"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def generate_filename(original_filename: str) -> str:
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported media format")

    return f"{uuid4().hex}{extension}"


def get_file_path(user_id: int, filename: str) -> Path:
    return get_user_storage(user_id) / filename


def is_video_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS
