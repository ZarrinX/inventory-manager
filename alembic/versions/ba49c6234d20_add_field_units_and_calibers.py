"""add field units and cartridge dropdown

Revision ID: ba49c6234d20
Revises: d46bc622a7ac
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ba49c6234d20"
down_revision: str | None = "d46bc622a7ac"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

CALIBERS = ["9mm", "22 LR", "22 Mini Mag", ".223", "5.56 NATO", ".308", "50 Beowulf (12.7x42mm)", "300 BLK", "6.5 Creedmoor"]


def upgrade() -> None:
    op.add_column("field_definitions", sa.Column("unit", sa.String(length=32), nullable=True))
    bind = op.get_bind()
    fields = sa.table("field_definitions", sa.column("id", sa.Integer), sa.column("field_key", sa.String), sa.column("field_type", sa.String))
    cartridge_id = bind.execute(sa.select(fields.c.id).where(fields.c.field_key == "cartridge")).scalar_one()
    bind.execute(fields.update().where(fields.c.id == cartridge_id).values(field_type="DROPDOWN"))
    options = sa.table("dropdown_options", sa.column("field_definition_id", sa.Integer), sa.column("stable_key", sa.String), sa.column("label", sa.String), sa.column("sort_order", sa.Integer), sa.column("enabled", sa.Boolean))
    bind.execute(options.insert(), [{"field_definition_id": cartridge_id, "stable_key": value, "label": value, "sort_order": index, "enabled": True} for index, value in enumerate(CALIBERS)])


def downgrade() -> None:
    op.drop_column("field_definitions", "unit")
