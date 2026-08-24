"""release UPCs from previously deleted products

Revision ID: c81d9e4a215f
Revises: ba49c6234d20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c81d9e4a215f"
down_revision: str | None = "ba49c6234d20"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    identifiers = sa.table("ammo_package_identifiers", sa.column("id", sa.Integer), sa.column("ammo_product_id", sa.Integer))
    products = sa.table("ammo_products", sa.column("id", sa.Integer), sa.column("deleted_at", sa.DateTime))
    op.execute(identifiers.delete().where(identifiers.c.ammo_product_id.in_(sa.select(products.c.id).where(products.c.deleted_at.is_not(None)))))


def downgrade() -> None:
    # Deleted UPC identifiers cannot be reconstructed safely.
    pass
