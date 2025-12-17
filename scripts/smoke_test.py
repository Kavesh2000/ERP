import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from pprint import pprint

print('PRODUCTS:')
prods = db.list_products()
pprint(prods)

print('\nSOURCES BEFORE:')
s = db.list_sources()
pprint(s)

print('\nINVENTORY BEFORE:')
inv = db.list_inventory()
pprint(inv)

# find 5L product id
pid = None
for p in prods:
    if p['name'] == '5L water':
        pid = p['id']
        break

print('\n5L product id:', pid)

if pid is None:
    print('No 5L product found; aborting test')
    raise SystemExit(1)

try:
    sale = db.record_order(product_id=pid, quantity=1, payment_method='Cash', created_by=1, use_bottle=True)
    print('\nSale created:')
    pprint(sale)
except Exception as e:
    print('\nOrder failed:', e)

print('\nSOURCES AFTER:')
pprint(db.list_sources())

print('\nINVENTORY AFTER:')
pprint(db.list_inventory())

print('\nMOVEMENTS (last 10):')
conn = db.connect()
cur = conn.cursor()
cur.execute('SELECT id, kind, ref_id, delta, reason, timestamp, user_id FROM movements ORDER BY id DESC LIMIT 10')
rows = cur.fetchall()
for r in rows:
    print(dict(r))
conn.close()
