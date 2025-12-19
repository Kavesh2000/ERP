"""Simple SQLite helpers for ERP prototype.

Tables:
- products(id INTEGER PRIMARY KEY, name TEXT, unit_price REAL)
- sales(id INTEGER PRIMARY KEY, product_id INTEGER, quantity INTEGER, unit_price REAL, total REAL, timestamp TEXT)

This module uses only Python's stdlib sqlite3.

"""
import os
DB_PATH = os.path.join(os.path.dirname(__file__), "erp.db")  # relative path to your project root


from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def get_db_path(base_dir: Path = Path(__file__).parent / "data") -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "erp.db"


def connect(db_path: Path | str | None = None):
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None):
    """Create tables and add default product (5L water at 40 KSH) if missing."""
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            unit_price REAL NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT DEFAULT 'Cash',
            timestamp TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    # create users table for simple auth
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )
    # ensure default product exists
    cur.execute("SELECT id FROM products WHERE name = ?", ("5L water",))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", ("5L water", 40.0))
    # ensure default users
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if cur.fetchone() is None:
        # NOTE: passwords stored in plain text for prototype only
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "admin", "admin"))
    cur.execute("SELECT id FROM users WHERE username = ?", ("user",))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("user", "user", "user"))
    conn.commit()
    # ensure inventory table exists (tracks product stock levels)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            product_id INTEGER UNIQUE NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
        """
    )
    # ensure sources table exists (central tanks / gallons where water comes from)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'L',
            quantity REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL
        )
        """
    )
    # mapping from product to source with factor (litres consumed per product unit)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS product_sources (
            product_id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL,
            factor REAL NOT NULL DEFAULT 1,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(source_id) REFERENCES sources(id)
        )
        """
    )
    # audit movements table for sources and inventory adjustments
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            ref_id INTEGER,
            delta REAL NOT NULL,
            reason TEXT,
            timestamp TEXT NOT NULL,
            user_id INTEGER
        )
        """
    )
    # API logs: records request metadata for auditing
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            user_id INTEGER,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            payload TEXT,
            status INTEGER,
            duration_ms INTEGER,
            ip TEXT
        )
        """
    )

    # price history for products (records price changes)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            old_price REAL,
            new_price REAL NOT NULL,
            changed_by INTEGER,
            reason TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    # Ensure sales.quantity is REAL (migrate if older INTEGER existed)
    try:
        cur.execute("PRAGMA table_info(sales)")
        cols = cur.fetchall()
        qty_col = None
        for c in cols:
            # c is sqlite3.Row with name and type
            if c[1] == 'quantity':
                qty_col = c
                break
        if qty_col is not None:
            col_type = qty_col[2].upper() if qty_col[2] else ''
            if col_type != 'REAL':
                # migrate table: create new table with quantity REAL, copy data
                cur.execute('ALTER TABLE sales RENAME TO sales_old')
                cur.execute(
                    """
                    CREATE TABLE sales (
                        id INTEGER PRIMARY KEY,
                        product_id INTEGER NOT NULL,
                        quantity REAL NOT NULL,
                        unit_price REAL NOT NULL,
                        total REAL NOT NULL,
                        payment_method TEXT DEFAULT 'Cash',
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY(product_id) REFERENCES products(id)
                    )
                    """
                )
                # copy rows, casting quantity to REAL
                cur.execute("INSERT INTO sales (id, product_id, quantity, unit_price, total, payment_method, timestamp) SELECT id, product_id, CAST(quantity AS REAL), unit_price, total, payment_method, timestamp FROM sales_old")
                cur.execute("DROP TABLE sales_old")
                conn.commit()
    except Exception:
        # if anything goes wrong, ignore migration (keep running)
        pass
    # ensure created_by column exists (add if missing)
    try:
        cur.execute("PRAGMA table_info(sales)")
        cols = [c[1] for c in cur.fetchall()]
        if 'created_by' not in cols:
            cur.execute("ALTER TABLE sales ADD COLUMN created_by INTEGER")
            conn.commit()
    except Exception:
        pass
    # ensure bottles_used column exists (track number of bottles consumed by a sale)
    try:
        cur.execute("PRAGMA table_info(sales)")
        cols = [c[1] for c in cur.fetchall()]
        if 'bottles_used' not in cols:
            cur.execute("ALTER TABLE sales ADD COLUMN bottles_used INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass
    # ensure bottle_price column exists (track price of bottles when used)
    try:
        cur.execute("PRAGMA table_info(sales)")
        cols = [c[1] for c in cur.fetchall()]
        if 'bottle_price' not in cols:
            cur.execute("ALTER TABLE sales ADD COLUMN bottle_price REAL DEFAULT 0")
            conn.commit()
    except Exception:
        pass
    # ensure client_timestamp column exists (store device/system timestamp for orders)
    try:
        cur.execute("PRAGMA table_info(sales)")
        cols = [c[1] for c in cur.fetchall()]
        if 'client_timestamp' not in cols:
            cur.execute("ALTER TABLE sales ADD COLUMN client_timestamp TEXT")
            conn.commit()
    except Exception:
        pass
    # --- Seed default sources and bottle stock ---
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        # ensure main tank (10000 L)
        cur.execute("SELECT id FROM sources WHERE name = ?", ("Main Tank",))
        r = cur.fetchone()
        if r is None:
            cur.execute("INSERT INTO sources (name, unit, quantity, last_updated) VALUES (?, ?, ?, ?)", ("Main Tank", 'L', 10000.0, now))
            main_tank_id = cur.lastrowid
        else:
            main_tank_id = r[0]

        # ensure water products exist (5L, 10L, 20L)
        cur.execute("SELECT id FROM products WHERE name = ?", ("5L water",))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", ("5L water", 40.0))
        cur.execute("SELECT id FROM products WHERE name = ?", ("10L water",))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", ("10L water", 70.0))
        cur.execute("SELECT id FROM products WHERE name = ?", ("20L water",))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", ("20L water", 120.0))

        # ensure empty bottle product types and inventory counts
        bottle_templates = [
            ("Empty 5L bottle", 0.0, 120.0),
            ("Empty 10L bottle", 0.0, 80.0),
            ("Empty 20L bottle", 0.0, 40.0),
        ]
        for name, price, initial_count in bottle_templates:
            cur.execute("SELECT id FROM products WHERE name = ?", (name,))
            r = cur.fetchone()
            if r is None:
                cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", (name, float(price)))
                pid = cur.lastrowid
            else:
                pid = r[0]
            # upsert inventory row for bottle counts
            cur.execute("SELECT id FROM inventory WHERE product_id = ?", (pid,))
            inv = cur.fetchone()
            if inv is None:
                cur.execute("INSERT INTO inventory (product_id, quantity, last_updated) VALUES (?, ?, ?)", (pid, float(initial_count), now))
            else:
                cur.execute("UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?", (float(initial_count), now, pid))

        # map water products to main tank with factors (litres per unit)
        mappings = [("5L water", 5.0), ("10L water", 10.0), ("20L water", 20.0)]
        for pname, factor in mappings:
            cur.execute("SELECT id FROM products WHERE name = ?", (pname,))
            r = cur.fetchone()
            if r:
                pid = r[0]
                cur.execute("SELECT product_id FROM product_sources WHERE product_id = ?", (pid,))
                if cur.fetchone() is None:
                    cur.execute("INSERT INTO product_sources (product_id, source_id, factor) VALUES (?, ?, ?)", (pid, main_tank_id, float(factor)))
                else:
                    cur.execute("UPDATE product_sources SET source_id = ?, factor = ? WHERE product_id = ?", (main_tank_id, float(factor), pid))

        conn.commit()
    except Exception:
        # non-fatal; continue
        pass
    conn.close()


### Sources (central tanks) helpers ###
def list_sources(db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, unit, quantity, last_updated FROM sources ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_source(source_id: int, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, unit, quantity, last_updated FROM sources WHERE id = ?", (source_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def add_source(name: str, unit: str = 'L', quantity: float = 0, db_path: Path | str | None = None):
    now = datetime.utcnow().isoformat() + 'Z'
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO sources (name, unit, quantity, last_updated) VALUES (?, ?, ?, ?)", (name, unit, float(quantity), now))
    sid = cur.lastrowid
    conn.commit()
    cur.execute("SELECT id, name, unit, quantity, last_updated FROM sources WHERE id = ?", (sid,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def update_source(source_id: int, name: str | None = None, unit: str | None = None, quantity: float | None = None, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    # build update pieces
    parts = []
    params = []
    if name is not None:
        parts.append('name = ?'); params.append(name)
    if unit is not None:
        parts.append('unit = ?'); params.append(unit)
    if quantity is not None:
        parts.append('quantity = ?'); params.append(float(quantity))
    if not parts:
        conn.close(); return get_source(source_id, db_path)
    parts.append('last_updated = ?'); params.append(datetime.utcnow().isoformat() + 'Z')
    params.append(source_id)
    sql = f"UPDATE sources SET {', '.join(parts)} WHERE id = ?"
    cur.execute(sql, tuple(params))
    conn.commit()
    cur.execute("SELECT id, name, unit, quantity, last_updated FROM sources WHERE id = ?", (source_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_source(source_id: int, db_path: Path | str | None = None) -> bool:
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return bool(changed)


def adjust_source_quantity(source_id: int, delta: float, db_path: Path | str | None = None) -> float:
    """Adjust source quantity by delta (can be negative). Returns new quantity. Raises ValueError on insufficient."""
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM sources WHERE id = ?", (source_id,))
    r = cur.fetchone()
    if r is None:
        if delta < 0:
            conn.close(); raise ValueError('insufficient stock')
        new_q = float(delta)
        now = datetime.utcnow().isoformat() + 'Z'
        cur.execute("INSERT INTO sources (id, name, unit, quantity, last_updated) VALUES (?, ?, ?, ?, ?)", (source_id, 'source', 'L', new_q, now))
        conn.commit(); conn.close(); return new_q
    cur_q = float(r[0])
    new_q = cur_q + float(delta)
    if new_q < 0:
        conn.close(); raise ValueError('insufficient stock')
    now = datetime.utcnow().isoformat() + 'Z'
    cur.execute("UPDATE sources SET quantity = ?, last_updated = ? WHERE id = ?", (new_q, now, source_id))
    conn.commit(); conn.close(); return new_q


### Product -> Source mapping helpers ###
def set_product_source(product_id: int, source_id: int, factor: float = 1.0, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT product_id FROM product_sources WHERE product_id = ?", (product_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO product_sources (product_id, source_id, factor) VALUES (?, ?, ?)", (product_id, source_id, float(factor)))
    else:
        cur.execute("UPDATE product_sources SET source_id = ?, factor = ? WHERE product_id = ?", (source_id, float(factor), product_id))
    conn.commit()
    cur.execute("SELECT product_id, source_id, factor FROM product_sources WHERE product_id = ?", (product_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_product_source(product_id: int, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT product_id, source_id, factor FROM product_sources WHERE product_id = ?", (product_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def list_product_sources(db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT ps.product_id, ps.source_id, ps.factor, p.name as product_name, s.name as source_name FROM product_sources ps JOIN products p ON p.id = ps.product_id JOIN sources s ON s.id = ps.source_id ORDER BY p.name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


### Inventory helpers ###
def list_inventory(db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT i.id, i.product_id, p.name as product_name, i.quantity, i.last_updated FROM inventory i JOIN products p ON p.id = i.product_id ORDER BY p.name"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_for_product(product_id: int, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, product_id, quantity, last_updated FROM inventory WHERE product_id = ?", (product_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def set_inventory(product_id: int, quantity: float, db_path: Path | str | None = None):
    """Create or update inventory record for a product. Returns the inventory row."""
    now = datetime.utcnow().isoformat() + 'Z'
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM inventory WHERE product_id = ?", (product_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO inventory (product_id, quantity, last_updated) VALUES (?, ?, ?)", (product_id, float(quantity), now))
        iid = cur.lastrowid
    else:
        cur.execute("UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?", (float(quantity), now, product_id))
        # fetch id
        cur.execute("SELECT id FROM inventory WHERE product_id = ?", (product_id,))
        iid = cur.fetchone()[0]
    conn.commit()
    cur.execute("SELECT id, product_id, quantity, last_updated FROM inventory WHERE id = ?", (iid,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def delete_inventory(product_id: int, db_path: Path | str | None = None) -> bool:
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM inventory WHERE product_id = ?", (product_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return bool(changed)


def adjust_inventory(product_id: int, delta: float, db_path: Path | str | None = None) -> float:
    """Adjust inventory quantity by delta (can be negative). Returns the new quantity.
    Raises ValueError if resulting quantity would be negative.
    """
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM inventory WHERE product_id = ?", (product_id,))
    r = cur.fetchone()
    if r is None:
        # no inventory row; treat as zero and create if delta positive
        if delta < 0:
            conn.close()
            raise ValueError("insufficient stock")
        new_q = float(delta)
        now = datetime.utcnow().isoformat() + 'Z'
        cur.execute("INSERT INTO inventory (product_id, quantity, last_updated) VALUES (?, ?, ?)", (product_id, new_q, now))
        conn.commit()
        conn.close()
        return new_q
    else:
        cur_q = float(r[0])
        new_q = cur_q + float(delta)
        if new_q < 0:
            conn.close()
            raise ValueError("insufficient stock")
        now = datetime.utcnow().isoformat() + 'Z'
        cur.execute("UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?", (new_q, now, product_id))
        conn.commit()
        conn.close()
        return new_q


def authenticate_user(username: str, password: str, db_path: Path | str | None = None) -> dict | None:
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE username = ? AND password = ?", (username, password))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


# --- User helpers ---
def get_user_by_username(username: str, db_path: Path | str | None = None) -> dict | None:
    """Return user row (id, username, role) or None if not found."""
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users WHERE username = ?", (username,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


def create_user(username: str, password: str = '', role: str = 'user', db_path: Path | str | None = None) -> dict:
    """Create a user with the given username/password/role and return the new row.
    If the user already exists, return the existing row.
    """
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password or '', role))
        conn.commit()
        uid = cur.lastrowid
    except Exception:
        # probably already exists; fall back to selecting
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        r = cur.fetchone()
        uid = r[0] if r else None
    if uid is None:
        conn.close()
        return get_user_by_username(username, db_path)
    cur.execute("SELECT id, username, role FROM users WHERE id = ?", (uid,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def list_products(db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, unit_price FROM products ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_sale(product_id: int, quantity: int = 1, db_path: Path | str | None = None) -> dict:
    # legacy function kept: no payment method
    return record_order(product_id=product_id, quantity=quantity, payment_method='Cash', db_path=db_path)


def record_order(product_id: int, quantity: float = 1, payment_method: str = 'Cash', order_date: str | None = None, created_by: int | None = None, use_bottle: bool = False, bottles_used: int | None = None, bottle_price: float = 0, client_timestamp: str | None = None, db_path: Path | str | None = None) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    conn = connect(db_path)
    cur = conn.cursor()
    # perform everything inside a transaction so adjustments + sale are atomic
    try:
        cur.execute("BEGIN")
        cur.execute("SELECT unit_price, name FROM products WHERE id = ?", (product_id,))
        r = cur.fetchone()
        if r is None:
            raise ValueError(f"product id {product_id} not found")
        unit_price = float(r["unit_price"])
        product_name = r["name"]
        total = unit_price * quantity
        
        # Add bottle price to total if using bottle
        if use_bottle and bottle_price > 0:
            # Calculate number of bottles
            bottles_count = 1
            if bottles_used is not None:
                bottles_count = int(bottles_used)
            else:
                import math
                bottles_count = int(quantity) if float(quantity).is_integer() else math.ceil(quantity)
            total += bottle_price * bottles_count

        # determine timestamp. Prefer client_timestamp (device/system time) when provided,
        # otherwise fall back to order_date or server UTC now.
        od_dt = None
        if client_timestamp:
            # client_timestamp expected to be ISO8601 with offset (e.g. 2025-12-11T14:03:00+03:00)
            try:
                print(f"DEBUG: Received client_timestamp: {client_timestamp!r}")
                cd = datetime.fromisoformat(client_timestamp)
                # If offset-aware, normalize to UTC
                if cd.tzinfo is not None:
                    od_dt = cd.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    # Treat naive client timestamp as local time: convert to UTC assuming it's already UTC
                    od_dt = cd
                print(f"DEBUG: Parsed client_timestamp -> UTC naive: {od_dt}")
            except Exception as e:
                print(f"DEBUG: Failed to parse client_timestamp: {e}")
                # fall through to order_date handling
                od_dt = None

        if od_dt is None and order_date:
            print(f"DEBUG: Received order_date: {order_date!r}")  # DEBUG
            try:
                od_dt = datetime.fromisoformat(order_date)
                print(f"DEBUG: Successfully parsed order_date as ISO datetime: {od_dt}")
            except Exception as e:
                print(f"DEBUG: fromisoformat failed for order_date: {e}, trying date-only fallback")
                try:
                    d = datetime.strptime(order_date, "%Y-%m-%d").date()
                    now_utc = datetime.utcnow()
                    od_dt = datetime.combine(d, now_utc.time())
                    print(f"DEBUG: Parsed order_date as date-only, attached current time: {od_dt}")
                except Exception:
                    raise ValueError("order_date must be YYYY-MM-DD or an ISO datetime (YYYY-MM-DDTHH:MM)")

        if od_dt is not None:
            # ensure not in the future relative to server UTC
            if od_dt > datetime.utcnow():
                raise ValueError("order_date cannot be in the future")
            ts = od_dt.replace(microsecond=0).isoformat() + 'Z'
        else:
            ts = datetime.utcnow().isoformat() + 'Z'

        # perform stock adjustments (source-based preferred)
        cur.execute("SELECT source_id, factor FROM product_sources WHERE product_id = ?", (product_id,))
        m = cur.fetchone()
        mapping = {'source_id': m[0], 'factor': float(m[1])} if m else None
        now_ts = datetime.utcnow().isoformat() + 'Z'

        if mapping:
            required = float(quantity) * float(mapping['factor'])
            cur.execute("SELECT quantity FROM sources WHERE id = ?", (mapping['source_id'],))
            srow = cur.fetchone()
            cur_q = float(srow[0]) if srow is not None else 0.0
            new_q = cur_q - required
            if new_q < 0:
                raise ValueError('insufficient stock for this order')
            cur.execute("UPDATE sources SET quantity = ?, last_updated = ? WHERE id = ?", (new_q, now_ts, mapping['source_id']))
            cur.execute("INSERT INTO movements (kind, ref_id, delta, reason, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?)", ('source', mapping['source_id'], -required, f'order:{product_id}', now_ts, created_by))
        else:
            # fallback to product inventory
            cur.execute("SELECT quantity FROM inventory WHERE product_id = ?", (product_id,))
            irow = cur.fetchone()
            cur_q = float(irow[0]) if irow is not None else 0.0
            new_q = cur_q - float(quantity)
            if new_q < 0:
                raise ValueError('insufficient stock for this order')
            if irow is None:
                cur.execute("INSERT INTO inventory (product_id, quantity, last_updated) VALUES (?, ?, ?)", (product_id, new_q, now_ts))
            else:
                cur.execute("UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?", (new_q, now_ts, product_id))
            cur.execute("INSERT INTO movements (kind, ref_id, delta, reason, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?)", ('inventory', product_id, -float(quantity), f'order:{product_id}', now_ts, created_by))

        # optional: decrement bottle inventory when requested or when `bottles_used` provided
        bottles_to_consume = None
        if bottles_used is not None:
            try:
                bottles_to_consume = int(bottles_used)
            except Exception:
                raise ValueError('bottles_used must be an integer')
            if bottles_to_consume < 0:
                raise ValueError('bottles_used cannot be negative')
        elif use_bottle:
            # compute bottles based on product size (existing behavior)
            bottle_pid = None
            try:
                if mapping:
                    bottle_name = f"Empty {int(mapping['factor'])}L bottle"
                    cur.execute("SELECT id FROM products WHERE name = ?", (bottle_name,))
                    prow = cur.fetchone()
                    if prow:
                        bottle_pid = prow[0]
                if bottle_pid is None:
                    cur.execute("SELECT id FROM products WHERE name LIKE ?", ("%Empty%",))
                    prow = cur.fetchone()
                    if prow:
                        bottle_pid = prow[0]
            except Exception:
                bottle_pid = None

            if bottle_pid is not None:
                import math
                bottles_to_consume = int(quantity) if float(quantity).is_integer() else math.ceil(quantity)

        # if we have a bottle count to consume, perform inventory decrement
        if bottles_to_consume is not None and bottles_to_consume > 0:
            # find bottle product id if not already determined
            if 'bottle_pid' not in locals() or bottle_pid is None:
                bottle_pid = None
                try:
                    if mapping:
                        bottle_name = f"Empty {int(mapping['factor'])}L bottle"
                        cur.execute("SELECT id FROM products WHERE name = ?", (bottle_name,))
                        prow = cur.fetchone()
                        if prow:
                            bottle_pid = prow[0]
                    if bottle_pid is None:
                        cur.execute("SELECT id FROM products WHERE name LIKE ?", ("%Empty%",))
                        prow = cur.fetchone()
                        if prow:
                            bottle_pid = prow[0]
                except Exception:
                    bottle_pid = None

            if bottle_pid is not None:
                cur.execute("SELECT quantity FROM inventory WHERE product_id = ?", (bottle_pid,))
                brow = cur.fetchone()
                cur_q = float(brow[0]) if brow else 0.0
                new_bq = cur_q - bottles_to_consume
                if new_bq < 0:
                    raise ValueError('insufficient bottle stock for this order')
                if brow is None:
                    cur.execute("INSERT INTO inventory (product_id, quantity, last_updated) VALUES (?, ?, ?)", (bottle_pid, new_bq, now_ts))
                else:
                    cur.execute("UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?", (new_bq, now_ts, bottle_pid))
                cur.execute("INSERT INTO movements (kind, ref_id, delta, reason, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?)", ('inventory', bottle_pid, -bottles_to_consume, f'order_bottle:{product_id}', now_ts, created_by))

        # insert sale row (include bottles_used and bottle_price when columns exist)
        cols = [c[1] for c in cur.execute("PRAGMA table_info(sales)").fetchall()]
        fields = ["product_id", "quantity", "unit_price", "total", "payment_method", "timestamp"]
        params = [product_id, quantity, unit_price, total, payment_method, ts]
        if 'created_by' in cols:
            fields.append('created_by')
            params.append(created_by)
        # persist bottles_used (0 if none)
        if 'bottles_used' in cols:
            fields.append('bottles_used')
            params.append(int(bottles_to_consume) if bottles_to_consume is not None else 0)
        # persist bottle_price
        if 'bottle_price' in cols:
            fields.append('bottle_price')
            params.append(bottle_price if use_bottle else 0)
        # include optional client_timestamp if present
        if 'client_timestamp' in cols:
            fields.append('client_timestamp')
            params.append(client_timestamp)
        placeholders = ', '.join(['?'] * len(fields))
        sql = f"INSERT INTO sales ({', '.join(fields)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(params))
        sale_id = cur.lastrowid
        conn.commit()
        # return sale including bottles_used/bottle_price/created_by when available
        select_cols = ["s.id", "s.product_id", "p.name as product_name", "s.quantity", "s.unit_price", "s.total", "s.payment_method", "s.timestamp"]
        if 'created_by' in cols:
            select_cols.append('s.created_by')
        if 'bottles_used' in cols:
            select_cols.append('s.bottles_used')
        if 'bottle_price' in cols:
            select_cols.append('s.bottle_price')
        if 'client_timestamp' in cols:
            select_cols.append('s.client_timestamp')
        sql = f"SELECT {', '.join(select_cols)} FROM sales s JOIN products p ON p.id = s.product_id WHERE s.id = ?"
        cur.execute(sql, (sale_id,))
        sale = dict(cur.fetchone())
        conn.close()
        return sale
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        # Re-raise so callers (API layer) receive an exception and can return
        # a proper HTTP error instead of returning null/None to the client.
        raise

# --- Price history helpers ---
def get_price_history(product_id: int, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, product_id, old_price, new_price, changed_by, timestamp, reason FROM price_history WHERE product_id = ? ORDER BY id DESC", (product_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
    


def list_sales(db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    # Include optional columns (bottles_used, bottle_price, created_by) if they exist in the sales table
    cols = [c[1] for c in cur.execute("PRAGMA table_info(sales)").fetchall()]
    select_cols = ["s.id", "s.product_id", "p.name as product_name", "s.quantity", "s.unit_price", "s.total", "s.timestamp"]
    if 'created_by' in cols:
        select_cols.append('s.created_by')
    if 'bottles_used' in cols:
        select_cols.append('s.bottles_used')
    if 'bottle_price' in cols:
        select_cols.append('s.bottle_price')
    sql = f"SELECT {', '.join(select_cols)} FROM sales s JOIN products p ON p.id = s.product_id ORDER BY s.id DESC"
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_orders(db_path: Path | str | None = None, date_iso: str | None = None, user_id: int | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    params = []
    where_clauses = []
    if date_iso:
        where_clauses.append("s.timestamp LIKE ?")
        params.append(f"{date_iso}%")
    if user_id is not None:
        where_clauses.append("s.created_by = ?")
        params.append(user_id)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    # Dynamically include optional columns when present in the sales table
    cols = [c[1] for c in cur.execute("PRAGMA table_info(sales)").fetchall()]
    select_cols = ["s.id", "s.product_id", "p.name as product_name", "s.quantity", "s.unit_price", "s.total", "s.payment_method", "s.timestamp"]
    if 'created_by' in cols:
        select_cols.append('s.created_by')
    if 'bottles_used' in cols:
        select_cols.append('s.bottles_used')
    if 'bottle_price' in cols:
        select_cols.append('s.bottle_price')

    sql = f"SELECT {', '.join(select_cols)} FROM sales s JOIN products p ON p.id = s.product_id {where_sql} ORDER BY s.id DESC"
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_movements(limit: int = 100, kind: str | None = None, ref_id: int | None = None, db_path: Path | str | None = None):
    """Return recent movements (audit) optionally filtered by kind ('source'|'inventory') or ref_id."""
    conn = connect(db_path)
    cur = conn.cursor()
    params = []
    where = []
    if kind:
        where.append('kind = ?')
        params.append(kind)
    if ref_id is not None:
        where.append('ref_id = ?')
        params.append(int(ref_id))
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    sql = f"SELECT id, kind, ref_id, delta, reason, timestamp, user_id FROM movements {where_sql} ORDER BY id DESC LIMIT ?"
    params.append(int(limit or 100))
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- API logs helpers (audit of incoming requests) ---

def log_api_call(method: str, path: str, status: int = 200, user_id: int | None = None, payload: str | None = None, duration_ms: int | None = None, ip: str | None = None, db_path: Path | str | None = None):
    """Insert a small audit row for an API request."""
    conn = connect(db_path)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat() + 'Z'
    cur.execute("INSERT INTO api_logs (timestamp, user_id, method, path, payload, status, duration_ms, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (now, user_id, method, path, payload, status, duration_ms, ip))
    conn.commit()
    conn.close()


def list_api_logs(limit: int = 100, db_path: Path | str | None = None):
    conn = connect(db_path)
    cur = conn.cursor()
    sql = "SELECT id, timestamp, user_id, method, path, payload, status, duration_ms, ip FROM api_logs ORDER BY id DESC LIMIT ?"
    cur.execute(sql, (int(limit or 100),))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_product(name: str, unit_price: float, db_path: Path | str | None = None) -> dict:
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, unit_price) VALUES (?, ?)", (name, float(unit_price)))
    pid = cur.lastrowid
    # record initial price in price_history
    now = datetime.utcnow().isoformat() + 'Z'
    try:
        cur.execute("INSERT INTO price_history (product_id, old_price, new_price, changed_by, timestamp, reason) VALUES (?, ?, ?, ?, ?, ?)", (pid, None, float(unit_price), None, now, 'initial'))
    except Exception:
        # ignore if price_history doesn't exist
        pass
    conn.commit()
    cur.execute("SELECT id, name, unit_price FROM products WHERE id = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def update_product(product_id: int, name: str, unit_price: float, db_path: Path | str | None = None) -> dict:
    conn = connect(db_path)
    cur = conn.cursor()
    # record previous price for history (best-effort)
    try:
        cur.execute("SELECT unit_price FROM products WHERE id = ?", (product_id,))
        prev = cur.fetchone()
        prev_price = float(prev[0]) if prev and prev[0] is not None else None
    except Exception:
        prev_price = None
    cur.execute("UPDATE products SET name = ?, unit_price = ? WHERE id = ?", (name, float(unit_price), product_id))
    now = datetime.utcnow().isoformat() + 'Z'
    try:
        cur.execute("INSERT INTO price_history (product_id, old_price, new_price, changed_by, timestamp, reason) VALUES (?, ?, ?, ?, ?, ?)", (product_id, prev_price, float(unit_price), None, now, 'update'))
    except Exception:
        pass
    conn.commit()
    cur.execute("SELECT id, name, unit_price FROM products WHERE id = ?", (product_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_product(product_id: int, db_path: Path | str | None = None) -> bool:
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id = ?", (product_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return bool(changed)


def daily_summary(date_iso: str | None = None, db_path: Path | str | None = None) -> dict:
    """Return totals (quantity and money) for a specific UTC date (YYYY-MM-DD). If date_iso is None use today's UTC date."""
    from datetime import datetime, timezone
    if date_iso is None:
        date_iso = datetime.utcnow().date().isoformat()
    conn = connect(db_path)
    cur = conn.cursor()
    # sum quantity and total for rows whose timestamp starts with date_iso
    cur.execute("SELECT SUM(quantity) as qty, SUM(total) as money FROM sales WHERE timestamp LIKE ?", (f"{date_iso}%",))
    r = cur.fetchone()
    conn.close()
    return {"date": date_iso, "total_quantity": int(r[0] or 0), "total_money": float(r[1] or 0.0)}
