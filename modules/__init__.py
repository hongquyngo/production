# modules/__init__.py
"""Manufacturing Module - Business Logic Components"""

from .bom import BOMManager
from .production import ProductionManager
from .inventory import InventoryManager
from .common import (
    get_products,
    get_warehouses,
    format_number,
    generate_order_number,
    calculate_date_range
)

__all__ = [
    'BOMManager',
    'ProductionManager', 
    'InventoryManager',
    'get_products',
    'get_warehouses',
    'format_number',
    'generate_order_number',
    'calculate_date_range'
]

__version__ = '1.0.0'