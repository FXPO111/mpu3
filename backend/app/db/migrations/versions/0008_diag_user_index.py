"""diag submissions user index

Revision ID: 0008_diag_user_index
Revises: 0007_user_progress
Create Date: 2026-02-27
"""

from alembic import op

revision = "0008_diag_user_index"
down_revision = "0007_user_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_diag_submission_user_id", "diagnostic_submissions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_diag_submission_user_id", table_name="diagnostic_submissions")