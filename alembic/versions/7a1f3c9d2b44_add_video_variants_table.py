"""add video variants table

Revision ID: 7a1f3c9d2b44
Revises: 2fb0d91560b7
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a1f3c9d2b44"
down_revision: Union[str, Sequence[str], None] = "2fb0d91560b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.Integer(), nullable=False),
        sa.Column("variant_type", sa.String(length=50), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
        sa.UniqueConstraint(
            "photo_id", "variant_type", name="uq_video_variant_photo_type"
        ),
    )
    op.create_index(op.f("ix_video_variants_id"), "video_variants", ["id"], unique=False)
    op.create_index(op.f("ix_video_variants_photo_id"), "video_variants", ["photo_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_video_variants_photo_id"), table_name="video_variants")
    op.drop_index(op.f("ix_video_variants_id"), table_name="video_variants")
    op.drop_table("video_variants")
