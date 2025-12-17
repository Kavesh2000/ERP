"""CLI entrypoint for the ERP prototype.

Usage (PowerShell):
    python -m main init
    python -m main sell --product-id 1 --quantity 2
    python -m main list
"""
import argparse
from pathlib import Path
import json
from db import init_db, list_products, record_sale, list_sales, get_db_path


def cmd_init(args):
    init_db()
    print(f"Initialized database at {get_db_path()}")
    print("Default products:")
    for p in list_products():
        print(f"  {p['id']}: {p['name']} — {p['unit_price']} KSH")


def cmd_sell(args):
    sale = record_sale(args.product_id, args.quantity)
    print("Recorded sale:")
    print(json.dumps(sale, indent=2))


def cmd_list(args):
    sales = list_sales()
    if not sales:
        print("No sales recorded yet.")
        return
    for s in sales:
        print(f"[{s['id']}] {s['timestamp']} — {s['product_name']} x{s['quantity']} @ {s['unit_price']} => {s['total']} KSH")


def main():
    parser = argparse.ArgumentParser(prog="erp", description="Minimal ERP CLI (sales recording)")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize database and default products")
    p_init.set_defaults(func=cmd_init)

    p_sell = sub.add_parser("sell", help="Record a sale")
    p_sell.add_argument("--product-id", type=int, required=True, help="Product ID to sell")
    p_sell.add_argument("--quantity", type=int, default=1, help="Quantity (integer)")
    p_sell.set_defaults(func=cmd_sell)

    p_list = sub.add_parser("list", help="List sales")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
