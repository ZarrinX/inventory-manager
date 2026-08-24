"""UPC/barcode resolution against active package identifiers (spec §24.1)."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AmmoPackageIdentifier, AmmoProduct


def resolve_identifier(db: Session, upc: str) -> AmmoPackageIdentifier | None:
    return db.scalar(
        select(AmmoPackageIdentifier).where(
            AmmoPackageIdentifier.upc == upc, AmmoPackageIdentifier.active.is_(True)
        )
    )


def resolve_upc(db: Session, upc: str) -> AmmoProduct | None:
    """Resolves a scanned/entered UPC to its product, with identifiers loaded.

    Multiple UPCs may resolve to the same product (spec §24.1); this always
    returns the product-level record, never a bare identifier.
    """
    identifier = resolve_identifier(db, upc)
    if not identifier:
        return None
    return db.scalar(
        select(AmmoProduct)
        .options(selectinload(AmmoProduct.identifiers))
        .where(AmmoProduct.id == identifier.ammo_product_id)
    )
