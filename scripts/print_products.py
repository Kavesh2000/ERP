import json
import db
print(json.dumps(db.list_products(), indent=2))
