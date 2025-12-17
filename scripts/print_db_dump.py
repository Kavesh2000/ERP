#!/usr/bin/env python3
"""Utility: print recent DB dump to stdout for manual inspection."""
from pprint import pprint
import db

if __name__ == '__main__':
    print("Products:")
    pprint(db.list_products())
    print('\nOrders (latest 200):')
    pprint(db.list_orders())
    print('\nInventory:')
    pprint(db.list_inventory())
    print('\nSources:')
    pprint(db.list_sources())
    print('\nProduct sources:')
    pprint(db.list_product_sources())
    print('\nMovements (latest 1000):')
    pprint(db.list_movements(limit=1000))
    print('\nAPI logs (latest 200):')
    pprint(db.list_api_logs(limit=200))
