#!/usr/bin/env python3
"""Initialize the SQLite database used by the app.

Usage:
  python scripts/init_db.py        # create database if missing
  python scripts/init_db.py --force  # delete existing DB and recreate
"""
import argparse
from pathlib import Path
import sys

import db


def main():
    parser = argparse.ArgumentParser(description='Initialize the ERP SQLite database')
    parser.add_argument('--force', action='store_true', help='Delete existing DB and recreate')
    args = parser.parse_args()

    db_path = db.get_db_path()
    if args.force and db_path.exists():
        print(f"Removing existing database at {db_path}")
        try:
            db_path.unlink()
        except Exception as e:
            print(f"Failed to remove {db_path}: {e}")
            sys.exit(1)

    try:
        db.init_db()
        print(f"Database initialized at: {db_path}")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
