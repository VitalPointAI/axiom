"""Tax categorization and reporting for NearTax."""

from .categories import (
    TaxCategory,
    CategoryResult,
    categorize_near_transaction,
    get_tax_treatment,
)

__all__ = [
    "TaxCategory",
    "CategoryResult", 
    "categorize_near_transaction",
    "get_tax_treatment",
]
