"""route days

Revision ID: 0005_route_days
Revises: 0004_route_cases
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_route_days"
down_revision = "0004_route_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),

        # "YYYY-MM-DD" in user's timezone (or UTC fallback)
        sa.Column("date_key", sa.String(10), nullable=False),

        # 1..N (incremental per user)
        sa.Column("day_index", sa.Integer(), nullable=False),

        sa.Column("status", sa.String(16), nullable=False, server_default="open"),

        # list[task], stored as JSON
        sa.Column("tasks_json", sa.JSON(), nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

        sa.UniqueConstraint("user_id", "date_key", name="uq_route_days_user_date_key"),
    )

    op.create_index("ix_route_days_user_day", "route_days", ["user_id", "day_index"])
    op.create_index("ix_route_days_user_date", "route_days", ["user_id", "date_key"])


def downgrade() -> None:
    op.drop_index("ix_route_days_user_date", table_name="route_days")
    op.drop_index("ix_route_days_user_day", table_name="route_days")
    op.drop_table("route_days")