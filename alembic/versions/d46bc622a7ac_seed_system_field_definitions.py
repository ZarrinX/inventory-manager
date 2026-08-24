"""seed system field definitions

Revision ID: d46bc622a7ac
Revises: 14736a9fea83
Create Date: 2026-08-24 15:32:01.297282

"""
import datetime
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd46bc622a7ac'
down_revision: str | None = '14736a9fea83'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

field_definitions_table = sa.table(
    "field_definitions",
    sa.column("field_key", sa.String),
    sa.column("display_name", sa.String),
    sa.column("field_type", sa.String),
    sa.column("value_type", sa.String),
    sa.column("required", sa.Boolean),
    sa.column("enabled", sa.Boolean),
    sa.column("searchable", sa.Boolean),
    sa.column("sort_order", sa.Integer),
    sa.column("system_field", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

# Built-in fields from spec §5.2. field_key values are stable identifiers —
# display_name may be renamed by an admin without affecting them (§9.1).
# field_type/value_type store the Enum *member name* (SQLAlchemy's default
# for `Enum(PyEnum)`), matching FieldControlType/FieldValueType in app/models/fields.py.
SYSTEM_FIELDS = [
    dict(field_key="upc", display_name="UPC", field_type="TEXT", value_type="TEXT",
         required=True, searchable=True, sort_order=0),
    dict(field_key="manufacturer", display_name="Manufacturer", field_type="TEXT", value_type="TEXT",
         required=True, searchable=True, sort_order=1),
    dict(field_key="product_line", display_name="Product Line", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=2),
    dict(field_key="manufacturer_sku", display_name="Manufacturer SKU", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=3),
    dict(field_key="cartridge", display_name="Cartridge / Caliber", field_type="TEXT", value_type="TEXT",
         required=True, searchable=True, sort_order=4),
    dict(field_key="bullet_weight_gr", display_name="Bullet Weight", field_type="TEXT", value_type="NUMBER",
         required=False, searchable=True, sort_order=5),
    dict(field_key="bullet_type", display_name="Bullet Type", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=6),
    dict(field_key="rounds_per_package", display_name="Rounds Per Box", field_type="TEXT", value_type="NUMBER",
         required=True, searchable=False, sort_order=7),
    dict(field_key="description", display_name="Description", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=8),
    dict(field_key="storage_location", display_name="Storage Location", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=9),
    dict(field_key="notes", display_name="Notes", field_type="TEXT", value_type="TEXT",
         required=False, searchable=True, sort_order=10),
]


def upgrade() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    op.bulk_insert(
        field_definitions_table,
        [
            {
                **field,
                "enabled": True,
                "system_field": True,
                "created_at": now,
                "updated_at": now,
            }
            for field in SYSTEM_FIELDS
        ],
    )


def downgrade() -> None:
    op.execute(field_definitions_table.delete().where(field_definitions_table.c.system_field.is_(True)))
