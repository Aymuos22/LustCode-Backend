"""Replace merchandise with the four requested rewards; preserve order history.

Revision ID: 8ae36dc2f109
Revises: 55b1518bb710
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8ae36dc2f109"
down_revision = "55b1518bb710"
branch_labels = None
depends_on = None

PRODUCTS = (
    (
        "premium-condom-pack",
        "Premium Condom Pack (12 pcs)",
        "A pack of 12 premium condoms, fulfilled manually within India.",
        500,
    ),
    (
        "water-based-lubricant",
        "Water-Based Lubricant (100ml)",
        "Water-based lubricant, 100ml, fulfilled manually within India.",
        1000,
    ),
    (
        "body-massage-oil",
        "Body Massage Oil (100ml)",
        "Body massage oil, 100ml, fulfilled manually within India.",
        2000,
    ),
    (
        "soft-adjustable-blindfold",
        "Soft Adjustable Blindfold",
        "A soft adjustable blindfold, fulfilled manually within India.",
        4000,
    ),
)


def product_table() -> sa.TableClause:
    return sa.table(
        "reward_products",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("coin_cost", sa.Integer()),
        sa.column("available_sizes", postgresql.JSONB()),
        sa.column("active", sa.Boolean()),
        sa.column("stock_quantity", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    products = product_table()
    # Retain old rows because historical orders reference them. Never reinterpret an
    # existing order, checkout key, ledger debit, or reserved inventory as a new product.
    op.execute(products.update().values(active=False))
    now = datetime.now(UTC)
    op.bulk_insert(
        products,
        [
            dict(
                id=slug,
                name=name,
                description=description,
                coin_cost=cost,
                available_sizes=[],
                active=True,
                stock_quantity=None,
                created_at=now,
            )
            for slug, name, description, cost in PRODUCTS
        ],
    )


def downgrade() -> None:
    ids = [row[0] for row in PRODUCTS]
    orders = sa.table("reward_orders", sa.column("reward_id", sa.String()))
    count = op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(orders).where(orders.c.reward_id.in_(ids))
    )
    if count:
        raise RuntimeError("Cannot remove reward products with order history")
    products = product_table()
    op.execute(products.delete().where(products.c.id.in_(ids)))
    # Keep retired products disabled. Their prior availability is not known, so a
    # rollback must not silently re-enable previously paused merchandise.
