ERP Prototype — Water Refilling Business

This is a minimal ERP prototype for a water refilling business. It provides a tiny CLI that records sales into an SQLite database.

Product included by default:
- 5 litres water — 40 KSH

Files:
- `main.py` — CLI to initialize DB, record sales, and list sales.
- `db.py` — database helpers (uses builtin sqlite3).
- `test_run.py` — simple smoke-test runner (no pytest required).
- `data/erp.db` — SQLite DB (created on first run).

Quick start (PowerShell):

```powershell
# from workspace root: C:\Users\<you>\Desktop\ERP
python -m main init
# record one sale of 1 unit (5L bottle)
python -m main sell --product-id 1 --quantity 1
# list sales
python -m main list
```

Notes:
- This is intentionally small and dependency-free (only requires Python 3.x). Next steps can include a web UI, reports, export, multi-product support, and authentication.

Web UI (local static site)
--------------------------

There is a lightweight static homepage in `web/` with a water-themed UI. To use it:

1. Copy the attached image (the one you provided) into `web/assets/images/` and rename it to `water1.jpg`.
2. (Optional) Add more images as `water2.jpg`, `water3.jpg`.
3. Serve the site locally with the included script:

```powershell
python serve.py
# open http://localhost:8000 in your browser
```

The homepage uses local images when available and falls back to online Unsplash images when offline.

Full web app (interactive)
---------------------------

If you'd like the interactive dashboard (login, record orders, daily summaries), run the Flask app (this serves the static UI and provides API endpoints):

1. Install requirements:

```powershell
pip install -r requirements.txt
```

2. Run the app:

```powershell
python app.py
# open http://localhost:5000/login
```

Demo accounts:
- admin / admin  (role: admin)
- user / user    (role: user)

Login note:
- The login form now asks you to "Login as" — select "Admin" or "User" before signing in. The backend verifies the selected role matches your account.

Behavior:
- After logging in the dashboard shows Sales and Orders.
- Create an order by choosing product and quantity — unit price auto-fills and total is calculated automatically.
- When creating an order you choose payment method (Cash or Mpesa). Orders are stored in the SQLite DB.
- Daily summary shows total units sold and total money for the current UTC date.

