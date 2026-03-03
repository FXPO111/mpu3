"""route cases (setup state)

Revision ID: 0004_route_cases
Revises: 0003_seed_default_plan_products
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_route_cases"
down_revision = "0003_seed_default_plan_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),

        sa.Column("topic", sa.String(32), nullable=False),          # alcohol|drugs|points|incident|unknown
        sa.Column("setup_status", sa.String(16), nullable=False),   # not_started|in_progress|complete
        sa.Column("setup_step", sa.Integer(), nullable=False),

        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("missing_json", sa.JSON(), nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

        sa.UniqueConstraint("user_id", name="uq_route_cases_user_id"),
    )

    op.create_index("ix_route_cases_user", "route_cases", ["user_id"])
    op.create_index("ix_route_cases_updated", "route_cases", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_route_cases_updated", table_name="route_cases")
    op.drop_index("ix_route_cases_user", table_name="route_cases")
    op.drop_table("route_cases")