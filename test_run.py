"""Simple smoke test — runs the init, records a sale, and prints the current sales.
This is runnable with plain `python test_run.py` (no pytest required).
"""
import os
from pathlib import Path
import db


def run_smoke():
    base = Path(__file__).parent
    # ensure db is fresh for the smoke run
    db_file = db.get_db_path()
    if db_file.exists():
        # avoid deleting user's data by accident; check env var
        if os.environ.get("ERP_ALLOW_CLEAN") == "1":
            db_file.unlink()
        else:
            print(f"Using existing DB at {db_file} (to force recreate set ERP_ALLOW_CLEAN=1)")
    db.init_db()
    # record one sale of default product id 1
    sale = db.record_sale(1, 1)
    print("Recorded sale:")
    print(sale)
    print("Sales list:")
    for s in db.list_sales():
        print(s)


if __name__ == "__main__":
    run_smoke()
