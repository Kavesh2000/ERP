"""Flask API + static file server for the ERP prototype.

Run:
  pip install -r requirements.txt
  python app.py

The app serves static files from `web/` and exposes simple API endpoints under `/api/`.
This is a prototype: authentication is minimal and passwords are stored as plain text for demo purposes only.
"""
from flask import Flask, request, jsonify, send_from_directory, session, redirect, g
from pathlib import Path
import db
from datetime import datetime
import os

app = Flask(__name__, static_folder='web', static_url_path='')
app.secret_key = 'dev-secret-erp'  # change for production

# simple timing for request logging
import time

@app.before_request
def _start_timer():
    g.request_start = time.time()

@app.after_request
def _log_request(response):
    try:
        # avoid logging static file requests
        if request.path.startswith('/assets') or request.path.startswith('/static'):
            return response
        # collect details
        payload = None
        try:
            payload = request.get_data(as_text=True)[:2000]
        except Exception:
            payload = None
        user = session.get('user') if session else None
        user_id = user.get('id') if user else None
        duration_ms = None
        if hasattr(g, 'request_start'):
            duration_ms = int((time.time() - g.request_start) * 1000)
        ip = request.remote_addr
        # log asynchronously best-effort (don't block response)
        try:
            db.log_api_call(method=request.method, path=request.path, status=response.status_code, user_id=user_id, payload=payload, duration_ms=duration_ms, ip=ip)
        except Exception:
            pass
    except Exception:
        pass
    return response


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/login')
def login_page():
    return app.send_static_file('login.html')


@app.route('/dashboard')
def dashboard_page():
    if 'user' not in session:
        return redirect('/')
    return app.send_static_file('index.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    expected_role = data.get('role')
    user = db.authenticate_user(username, password)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    if expected_role and user.get('role') != expected_role:
        return jsonify({'error': f'Invalid role — user is {user.get("role")}, not {expected_role}'}), 403
    session['user'] = {'id': user['id'], 'username': user['username'], 'role': user['role']}
    return jsonify({'ok': True, 'user': session['user']})


@app.route('/api/whoami')
def api_whoami():
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify({'user': u})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('user', None)
    return jsonify({'ok': True})


@app.route('/api/products')
def api_products():
    prods = db.list_products()
    return jsonify(prods)


@app.route('/api/products', methods=['POST'])
def api_create_product():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    name = data.get('name')
    unit_price = data.get('unit_price')
    if not name or unit_price is None:
        return jsonify({'error': 'name and unit_price required'}), 400
    p = db.add_product(name, float(unit_price))
    return jsonify(p), 201


@app.route('/api/products/<int:product_id>', methods=['PUT'])
def api_update_product(product_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    name = data.get('name')
    unit_price = data.get('unit_price')

    if unit_price is not None and name is None:
        cur = db.connect().cursor()
        cur.execute("SELECT name FROM products WHERE id = ?", (product_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'product not found'}), 404
        name = row[0]

    if not name or unit_price is None:
        return jsonify({'error': 'name and unit_price required'}), 400
    p = db.update_product(product_id, name, float(unit_price))
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify(p)


@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def api_delete_product(product_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    ok = db.delete_product(product_id)
    if not ok:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/products/<int:product_id>/history')
def api_product_price_history(product_id):
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    hist = db.get_price_history(product_id)
    return jsonify(hist)


@app.route('/api/orders', methods=['GET', 'POST'])
def api_orders():
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    if request.method == 'GET':
        date = request.args.get('date')
        if u.get('role') == 'admin':
            return jsonify(db.list_orders(date_iso=date))
        else:
            return jsonify(db.list_orders(date_iso=date, user_id=u.get('id')))
    data = request.get_json() or {}
    try:
        product_id = int(data.get('product_id'))
    except Exception:
        return jsonify({'error': 'invalid product_id'}), 400
    try:
        quantity = float(data.get('quantity', 1))
    except Exception:
        return jsonify({'error': 'invalid quantity'}), 400
    payment_method = data.get('payment_method', 'Cash')
    order_date = data.get('order_date')
    try:
        bottle_price = float(data.get('bottle_price', 0))
    except Exception:
        bottle_price = 0
    client_timestamp = data.get('client_timestamp')
    try:
        use_bottle = bool(data.get('use_bottle'))
        try:
            bottles_used = data.get('bottles_used')
            bottles_used = int(bottles_used) if bottles_used is not None else None
        except Exception:
            bottles_used = None
        order = db.record_order(
            product_id=product_id,
            quantity=quantity,
            payment_method=payment_method,
            order_date=order_date,
            created_by=u.get('id'),
            use_bottle=use_bottle,
            bottles_used=bottles_used,
            bottle_price=bottle_price,
            client_timestamp=client_timestamp
        )
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': 'failed to create order', 'detail': str(e)}), 500
    return jsonify(order)


@app.route('/api/stock', methods=['GET'])
def api_list_stock():
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify(db.list_inventory())


@app.route('/api/stock', methods=['POST'])
def api_create_stock():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    try:
        product_id = int(data.get('product_id'))
        quantity = float(data.get('quantity', 0))
    except Exception:
        return jsonify({'error': 'invalid payload'}), 400
    rec = db.set_inventory(product_id=product_id, quantity=quantity)
    return jsonify(rec), 201


@app.route('/api/stock/<int:product_id>', methods=['PUT'])
def api_update_stock(product_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    try:
        quantity = float(data.get('quantity'))
    except Exception:
        return jsonify({'error': 'invalid quantity'}), 400
    rec = db.set_inventory(product_id=product_id, quantity=quantity)
    return jsonify(rec)


@app.route('/api/stock/<int:product_id>', methods=['DELETE'])
def api_delete_stock(product_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    ok = db.delete_inventory(product_id)
    if not ok:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/sources', methods=['GET'])
def api_list_sources():
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify(db.list_sources())


@app.route('/api/sources', methods=['POST'])
def api_create_source():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    name = data.get('name')
    unit = data.get('unit', 'L')
    try:
        quantity = float(data.get('quantity', 0))
    except Exception:
        return jsonify({'error': 'invalid quantity'}), 400
    if not name:
        return jsonify({'error': 'name required'}), 400
    s = db.add_source(name=name, unit=unit, quantity=quantity)
    return jsonify(s), 201


@app.route('/api/sources/<int:source_id>', methods=['PUT'])
def api_update_source(source_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    name = data.get('name')
    unit = data.get('unit')
    quantity = data.get('quantity')
    try:
        q = float(quantity) if quantity is not None else None
    except Exception:
        return jsonify({'error': 'invalid quantity'}), 400
    s = db.update_source(source_id, name=name, unit=unit, quantity=q)
    if not s:
        return jsonify({'error': 'not found'}), 404
    return jsonify(s)


@app.route('/api/sources/<int:source_id>', methods=['DELETE'])
def api_delete_source(source_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    ok = db.delete_source(source_id)
    if not ok:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/product_sources', methods=['GET'])
def api_list_product_sources():
    u = session.get('user')
    if not u:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify(db.list_product_sources())


@app.route('/api/product_sources', methods=['POST'])
def api_set_product_source():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json() or {}
    try:
        product_id = int(data.get('product_id'))
        source_id = int(data.get('source_id'))
        factor = float(data.get('factor', 1.0))
    except Exception:
        return jsonify({'error': 'invalid payload'}), 400
    rec = db.set_product_source(product_id=product_id, source_id=source_id, factor=factor)
    return jsonify(rec), 201


@app.route('/api/product_sources/<int:product_id>', methods=['DELETE'])
def api_delete_product_source(product_id):
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    conn = db.connect()
    cur = conn.cursor()
    cur.execute('DELETE FROM product_sources WHERE product_id = ?', (product_id,))
    changed = cur.rowcount
    conn.commit(); conn.close()
    if not changed:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/movements', methods=['GET'])
def api_list_movements():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100
    kind = request.args.get('kind')
    ref_id = request.args.get('ref_id')
    try:
        ref_id_val = int(ref_id) if ref_id is not None and ref_id != '' else None
    except Exception:
        ref_id_val = None
    rows = db.list_movements(limit=limit, kind=kind or None, ref_id=ref_id_val)
    return jsonify(rows)


@app.route('/api/debug/logs', methods=['GET'])
def api_debug_logs():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    try:
        limit = int(request.args.get('limit', 200))
    except Exception:
        limit = 200
    logs = db.list_api_logs(limit=limit)
    return jsonify(logs)


@app.route('/api/upload_image', methods=['POST'])
def api_upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'no file provided'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'empty filename'}), 400
    images_dir = Path(app.static_folder) / 'assets' / 'images'
    images_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f.filename.replace('..', '_')
    dest = images_dir / safe_name
    f.save(dest)
    return jsonify({'url': f"/assets/images/{safe_name}"}), 201


@app.route('/api/debug/dump', methods=['GET'])
def api_debug_dump():
    """Admin-only: return a JSON dump of main tables for debugging/backup."""
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    try:
        dump = {
            'products': db.list_products(),
            'orders': db.list_orders(),
            'inventory': db.list_inventory(),
            'sources': db.list_sources(),
            'product_sources': db.list_product_sources(),
            'movements': db.list_movements(limit=1000),
            'api_logs': db.list_api_logs(limit=1000)
        }
        return jsonify(dump)
    except Exception as e:
        return jsonify({'error': 'failed to generate dump', 'detail': str(e)}), 500


@app.route('/api/debug/export', methods=['GET'])
def api_debug_export():
    """Admin-only: export tables as CSV or a ZIP of CSV files.

    Query params:
      table=<name>|all  (e.g., orders, products)
      format=csv|zip     (default csv; if table=all, zip is better)
    """
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    table = request.args.get('table', 'all')
    fmt = request.args.get('format', 'csv')

    # helper to create CSV string from rows (list of dicts)
    import io, csv, zipfile, datetime

    def rows_to_csv_bytes(rows):
        out = io.StringIO()
        if not rows:
            return out.getvalue().encode('utf-8')
        # use keys of first row as header
        keys = list(rows[0].keys())
        writer = csv.writer(out)
        writer.writerow(keys)
        for r in rows:
            writer.writerow([r.get(k, '') for k in keys])
        return out.getvalue().encode('utf-8')

    try:
        choices = {
            'products': db.list_products,
            'orders': db.list_orders,
            'inventory': db.list_inventory,
            'sources': db.list_sources,
            'product_sources': db.list_product_sources,
            'movements': lambda: db.list_movements(limit=100000),
            'api_logs': lambda: db.list_api_logs(limit=100000)
        }
        if table != 'all' and table not in choices:
            return jsonify({'error': 'unknown table'}), 400

        if table == 'all':
            # package all as zip
            bio = io.BytesIO()
            with zipfile.ZipFile(bio, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for name, fn in choices.items():
                    rows = fn()
                    data = rows_to_csv_bytes(rows)
                    zf.writestr(f"{name}.csv", data)
            bio.seek(0)
            fname = f"db_export_all_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.zip"
            return (bio.getvalue(), 200, {
                'Content-Type': 'application/zip',
                'Content-Disposition': f'attachment; filename="{fname}"'
            })
        else:
            rows = choices[table]()
            data = rows_to_csv_bytes(rows)
            fname = f"{table}_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
            return (data, 200, {
                'Content-Type': 'text/csv; charset=utf-8',
                'Content-Disposition': f'attachment; filename="{fname}"'
            })
    except Exception as e:
        return jsonify({'error': 'export failed', 'detail': str(e)}), 500


@app.route('/api/daily_summary')
def api_daily_summary():
    u = session.get('user')
    if not u or u.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    date = request.args.get('date')
    return jsonify(db.daily_summary(date))


@app.route('/api/images')
def api_images():
    images_dir = Path(app.static_folder) / 'assets' / 'images'
    out = []
    if images_dir.exists():
        for f in sorted(images_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif'):
                out.append(f"/assets/images/{f.name}")
    return jsonify(out)


if __name__ == '__main__':
    db.init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
