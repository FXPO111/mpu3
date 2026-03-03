"""user progress (cabinet state)

Revision ID: 0007_user_progress
Revises: 0006_program_products_backfill
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_user_progress"
down_revision = "0006_program_products_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),

        # Полное состояние кабинета (json)
        sa.Column("state_json", sa.JSON(), nullable=False),

        # на будущее (миграции структуры state_json)
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

        sa.UniqueConstraint("user_id", name="uq_user_progress_user_id"),
    )

    op.create_index("ix_user_progress_user_id", "user_progress", ["user_id"])
    op.create_index("ix_user_progress_updated", "user_progress", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_user_progress_updated", table_name="user_progress")
    op.drop_index("ix_user_progress_user_id", table_name="user_progress")
    op.drop_table("user_progress")