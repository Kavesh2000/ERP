import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import list_products, add_product

# Desired products
wanted = [
    ("10 litres", 80.0),
    ("20 litres", 150.0),
]
# compute per-litre price using 10 litres item (preferred)
per_litre_price = 80.0 / 10.0
wanted.append(("1 litre", per_litre_price))

existing = {p['name']: p for p in list_products()}
for name, price in wanted:
    if name in existing:
        print(f"Exists: {name} @ {existing[name]['unit_price']} KSH")
    else:
        p = add_product(name, price)
        print(f"Added: {p['name']} (id={p['id']}) @ {p['unit_price']} KSH")

print('\nAll products:')
for p in list_products():
    print(f" - {p['id']}: {p['name']} @ {p['unit_price']} KSH")
