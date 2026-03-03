"""seed default plan products

Revision ID: 0003_seed_default_plan_products
Revises: 0002_diagnostic_submissions
Create Date: 2026-02-19
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0003_seed_default_plan_products"
down_revision = "0002_diagnostic_submissions"
branch_labels = None
depends_on = None

SEED_TAG = "default_plans_v1"


def _upsert(code: str, plan: str, name: str, price_cents: int, valid_days: int, ai_credits: int) -> None:
    bind = op.get_bind()

    upsert_stmt = sa.text(
        """
        INSERT INTO products (id, code, type, name_de, name_en, price_cents, currency, stripe_price_id, metadata, active)
        VALUES (
          CAST(:id AS uuid),
          :code,
          'program',
          :name,
          :name,
          :price_cents,
          'EUR',
          NULL,
          jsonb_build_object(
            'plan', CAST(:plan AS text),
            'valid_days', CAST(:valid_days AS integer),
            'ai_credits', CAST(:ai_credits AS integer),
            'seed_tag', CAST(:seed_tag AS text)
          ),
          true
        )
        ON CONFLICT (code) DO UPDATE SET
          type = CASE WHEN products.type IS NULL OR products.type = '' THEN EXCLUDED.type ELSE products.type END,
          name_de = CASE WHEN products.name_de IS NULL OR products.name_de = '' THEN EXCLUDED.name_de ELSE products.name_de END,
          name_en = CASE WHEN products.name_en IS NULL OR products.name_en = '' THEN EXCLUDED.name_en ELSE products.name_en END,
          currency = CASE WHEN products.currency IS NULL OR products.currency = '' THEN EXCLUDED.currency ELSE products.currency END,
          metadata = COALESCE(products.metadata::jsonb, '{}'::jsonb)
            || jsonb_build_object(
                 'plan', EXCLUDED.metadata::jsonb->>'plan',
                 'valid_days', EXCLUDED.metadata::jsonb->>'valid_days',
                 'ai_credits', EXCLUDED.metadata::jsonb->>'ai_credits',
                 'seed_tag', COALESCE(products.metadata::jsonb->>'seed_tag', CAST(:seed_tag AS text))
               ),
          active = COALESCE(products.active, true)
        """
    )

    bind.execute(
        upsert_stmt,
        {
            "id": str(uuid4()),
            "code": code,
            "plan": plan,
            "name": name,
            "price_cents": price_cents,
            "seed_tag": SEED_TAG,
            "valid_days": valid_days,
            "ai_credits": ai_credits,
        },
    )


def upgrade() -> None:
    _upsert("PLAN_START", "start", "Start", 23000, 14, 1200)
    _upsert("PLAN_PRO", "pro", "Pro", 70000, 30, 8000)
    _upsert("PLAN_INTENSIVE", "intensive", "Intensive", 150000, 45, 15000)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM products
            WHERE code IN ('PLAN_START', 'PLAN_PRO', 'PLAN_INTENSIVE')
              AND COALESCE(metadata::jsonb->>'seed_tag', '') = :seed_tag
            """
        ),
        {"seed_tag": SEED_TAG},
    )