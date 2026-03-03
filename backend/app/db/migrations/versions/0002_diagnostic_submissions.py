"""diagnostic submissions

Revision ID: 0002_diagnostic_submissions
Revises: 0001_initial
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_diagnostic_submissions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reasons", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("other_reason", sa.String(120), nullable=True),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("history", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("recommended_plan", sa.String(32), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diag_submission_created", "diagnostic_submissions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_diag_submission_created", table_name="diagnostic_submissions")
    op.drop_table("diagnostic_submissions")