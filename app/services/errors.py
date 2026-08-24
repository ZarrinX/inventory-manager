class InventoryServiceError(Exception):
    """Base class for service-layer errors routers translate into HTTP responses."""


class DuplicateUpcError(InventoryServiceError):
    """A package identifier already exists for the given UPC."""


class ProductNotFoundError(InventoryServiceError):
    """No active AmmoProduct matches the given lookup."""


class NegativeInventoryError(InventoryServiceError):
    """The requested transaction would result in a negative balance (spec §6.2)."""
