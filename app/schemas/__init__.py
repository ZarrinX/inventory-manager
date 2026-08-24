from app.schemas.ammo import (
    AmmoPackageIdentifierOut,
    AmmoPackageIdentifierUpdate,
    AmmoProductCreate,
    AmmoProductOut,
    AmmoProductDetail,
    AmmoProductUpdate,
    InventoryPage,
)
from app.schemas.audit import AuditEventOut
from app.schemas.fields import (
    CustomFieldValuesUpdate,
    DropdownOptionCreate,
    DropdownOptionOut,
    DropdownOptionUpdate,
    FieldDefinitionCreate,
    FieldDefinitionOut,
    FieldDefinitionUpdate,
)
from app.schemas.preferences import InventoryViewPreferenceOut, InventoryViewPreferenceUpdate
from app.schemas.locations import LocationCreate, LocationOut, LocationUpdate
from app.schemas.scan import ScanResult
from app.schemas.transactions import (
    InventoryTransactionCreate,
    InventoryTransactionOut,
    TransactionReverseRequest,
    TransactionSubmissionOut,
    TransactionHistoryItem,
    TransactionHistoryPage,
)

AmmoProductDetail.model_rebuild(_types_namespace={"InventoryTransactionOut": InventoryTransactionOut})

__all__ = [
    "AmmoPackageIdentifierOut",
    "AmmoProductOut",
    "AmmoProductDetail",
    "InventoryPage",
    "AmmoProductCreate",
    "AmmoProductUpdate",
    "AmmoPackageIdentifierUpdate",
    "AuditEventOut",
    "FieldDefinitionOut",
    "FieldDefinitionCreate",
    "FieldDefinitionUpdate",
    "DropdownOptionOut",
    "DropdownOptionCreate",
    "DropdownOptionUpdate",
    "CustomFieldValuesUpdate",
    "InventoryViewPreferenceOut",
    "InventoryViewPreferenceUpdate",
    "LocationOut",
    "LocationCreate",
    "LocationUpdate",
    "InventoryTransactionCreate",
    "InventoryTransactionOut",
    "TransactionReverseRequest",
    "TransactionSubmissionOut",
    "TransactionHistoryItem",
    "TransactionHistoryPage",
    "ScanResult",
]
