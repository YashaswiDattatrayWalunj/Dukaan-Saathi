"""Saved shop data (SQLite). One file: data/dukaan.db, created on first run.
Every shop table has a merchant_id and every query filters by it. The signed-in merchant is held in a context
variable that only the login check (auth.py) sets; with no merchant set, shop queries fail instead of leaking data."""
import contextvars
import csv
import datetime as dt
import io
import math
import os
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = {
    "sales": ["date", "product_id", "qty"],
    "stock": ["product_id", "name_en", "name_hi", "name_mr", "price", "cost", "stock", "lead_days", "festival_uplift"],
    "khata": ["name", "amount", "days_overdue"],
    "customers": ["name", "visit_every_days", "days_away", "avg_bill"],
}
DDL = """
CREATE TABLE IF NOT EXISTS merchants(id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT UNIQUE, shop_name TEXT, owner_name TEXT, pw_hash TEXT, lang TEXT DEFAULT 'en', is_demo INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS products(merchant_id INTEGER, id TEXT, name_en TEXT, name_hi TEXT, name_mr TEXT, price REAL, cost REAL, stock REAL, lead_days INTEGER, festival_uplift REAL, PRIMARY KEY(merchant_id, id));
CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, date TEXT, product_id TEXT, qty INTEGER, stock_taken REAL DEFAULT 0, src TEXT DEFAULT 'import');
CREATE TABLE IF NOT EXISTS khata(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, amount REAL, due_date TEXT, phone TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, visit_every_days INTEGER, last_visit TEXT, avg_bill REAL, phone TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS meta(merchant_id INTEGER, k TEXT, v TEXT, PRIMARY KEY(merchant_id, k));
CREATE TABLE IF NOT EXISTS plan_state(merchant_id INTEGER, day TEXT, key TEXT, status TEXT, PRIMARY KEY(merchant_id, day, key));
CREATE TABLE IF NOT EXISTS paytm_transactions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER NOT NULL,
 source_transaction_id TEXT NOT NULL, txn_date TEXT NOT NULL, amount REAL NOT NULL,
 status TEXT NOT NULL, order_id TEXT DEFAULT '', payment_mode TEXT DEFAULT '',
 txn_type TEXT DEFAULT 'payment', raw_json TEXT DEFAULT '{}', imported_at TEXT NOT NULL,
 UNIQUE(merchant_id, source_transaction_id));
CREATE INDEX IF NOT EXISTS i_sales ON sales(merchant_id, date);
CREATE INDEX IF NOT EXISTS i_khata ON khata(merchant_id);
CREATE INDEX IF NOT EXISTS i_cust ON customers(merchant_id);
"""

_mid = contextvars.ContextVar("merchant_id", default=None)


def set_merchant(merchant_id):
    _mid.set(int(merchant_id))


def mid():
    m = _mid.get()
    if m is None:
        raise PermissionError("No merchant is signed in")
    return m


def conn():
    c = sqlite3.connect(os.getenv("SAATHI_DB") or str(ROOT / "data" / "dukaan.db"))
    c.row_factory = sqlite3.Row
    return c


def today():
    return dt.date.fromisoformat(os.getenv("SAATHI_TODAY")) if os.getenv("SAATHI_TODAY") else dt.date.today()


def mode():
    with conn() as c:
        r = c.execute("SELECT v FROM meta WHERE merchant_id=? AND k='mode'", (mid(),)).fetchone()
    return r["v"] if r else None


_ready = set()


def init():
    with conn() as c:
        c.executescript(DDL)


def ensure():
    """Create the tables the first time they are needed in this run."""
    key = os.getenv("SAATHI_DB") or "default"
    if key not in _ready:
        init()
        _ready.add(key)


# ---------- validation helpers ----------
def _num(v, name, lo=0, hi=10_000_000):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if math.isnan(x) or x < lo or x > hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return x


def _txt(v, name, mx=80):
    s = str(v or "").strip()
    if not s:
        raise ValueError(f"{name} is required")
    return s[:mx]


def _date(v, name):
    try:
        return dt.date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise ValueError(f"{name} must be a date like 2026-10-31")


def phone_clean(v):
    """Optional Indian mobile number -> '91XXXXXXXXXX' (digits only), or '' when empty."""
    d = re.sub(r"\D", "", str(v or ""))
    if not d:
        return ""
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if not re.fullmatch(r"[6-9]\d{9}", d):
        raise ValueError("Mobile number must be 10 digits, like 9876543210")
    return "91" + d


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "item"


# ---------- sample data ----------
_P = [("parle", "Parle-G", "पार्ले-जी", "पार्ले-जी", 10, 8, 38, 2, 1.3, 30, .04),
      ("milk", "Amul milk", "अमूल दूध", "अमूल दूध", 32, 29, 70, 1, 1.15, 24, .01),
      ("maggi", "Maggi", "मैगी", "मॅगी", 14, 11, 90, 3, 1.1, 12, 0),
      ("tea", "Tata Tea 250g", "टाटा चाय 250g", "टाटा चहा 250g", 135, 112, 30, 3, 1.15, 3, .02),
      ("atta", "Atta 5kg", "आटा 5kg", "आटा 5kg", 285, 250, 6, 2, 1.25, 2.5, .03),
      ("sweets", "Sweets box", "मिठाई बॉक्स", "मिठाई बॉक्स", 120, 90, 24, 2, 2.0, 4, .1)]


def _rnd(i, d):
    x = math.sin(i * 12.9898 + d * 78.233) * 43758.5453
    return x - math.floor(x)


def _clear(c):
    m = mid()
    for t in ("products", "sales", "khata", "customers", "plan_state"):
        c.execute(f"DELETE FROM {t} WHERE merchant_id=?", (m,))


def seed_sample():
    t, m = today(), mid()
    with conn() as c:
        c.executescript(DDL)
        _clear(c)
        for i, p in enumerate(_P):
            c.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?)", (m,) + p[:9])
            for d in range(13, -1, -1):
                day = t - dt.timedelta(days=d)
                wk = 1.25 if day.weekday() >= 5 else 1
                q = max(0, int(p[9] * (1 + p[10] * (13 - d) / 2) * wk * (.85 + .3 * _rnd(i, d)) + .5))
                c.execute("INSERT INTO sales(merchant_id,date,product_id,qty) VALUES(?,?,?,?)", (m, day.isoformat(), p[0], q))
        for n, a, od in [("Sunita Devi", 780, 15), ("Meena Tai", 1250, 9), ("Rahul Sharma", 500, 3), ("Imran Bhai", 320, -2)]:
            c.execute("INSERT INTO khata(merchant_id,name,amount,due_date) VALUES(?,?,?,?)", (m, n, a, (t - dt.timedelta(days=od)).isoformat()))
        for n, ev, gone, avg in [("Priya Nair", 7, 24, 420), ("Vikas Patil", 5, 19, 260), ("Anita Joshi", 10, 31, 680)]:
            c.execute("INSERT INTO customers(merchant_id,name,visit_every_days,last_visit,avg_bill) VALUES(?,?,?,?,?)", (m, n, ev, (t - dt.timedelta(days=gone)).isoformat(), avg))
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,'mode','sample')", (m,))


def reset(kind):
    if kind == "sample":
        return seed_sample()
    if kind == "empty":
        with conn() as c:
            _clear(c)
            c.execute("INSERT OR REPLACE INTO meta VALUES(?,'mode','mine')", (mid(),))
        return
    raise ValueError("kind must be sample or empty")


# ---------- shop actions ----------
def upsert_product(d):
    name = _txt(d.get("name_en"), "Item name")
    pid = slug(name)
    row = (mid(), pid, name, str(d.get("name_hi") or "").strip()[:80], str(d.get("name_mr") or "").strip()[:80],
           _num(d.get("price"), "Selling price"), _num(d.get("cost"), "Cost price"), _num(d.get("stock"), "Stock"),
           int(_num(d.get("lead_days", 2), "Supplier days", 0, 60)), _num(d.get("festival_uplift", 1.1), "Festival uplift", 0.5, 5))
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO products VALUES(?,?,?,?,?,?,?,?,?,?)", row)
    return pid


def record_sale(pid, qty=1, date=None):
    qty = int(_num(qty, "Quantity", 1, 100000))
    date = _date(date, "Date") if date else today().isoformat()
    m = mid()
    with conn() as c:
        p = c.execute("SELECT stock FROM products WHERE merchant_id=? AND id=?", (m, pid)).fetchone()
        if not p:
            raise ValueError("Unknown item")
        take = min(p["stock"], qty)
        c.execute("UPDATE products SET stock=stock-? WHERE merchant_id=? AND id=?", (take, m, pid))
        c.execute("INSERT INTO sales(merchant_id,date,product_id,qty,stock_taken,src) VALUES(?,?,?,?,?,'app')", (m, date, pid, qty, take))


def undo_sale():
    m = mid()
    with conn() as c:
        r = c.execute("SELECT * FROM sales WHERE merchant_id=? AND src='app' ORDER BY id DESC LIMIT 1", (m,)).fetchone()
        if not r:
            return None
        c.execute("UPDATE products SET stock=stock+? WHERE merchant_id=? AND id=?", (r["stock_taken"], m, r["product_id"]))
        c.execute("DELETE FROM sales WHERE id=? AND merchant_id=?", (r["id"], m))
        return r["product_id"]


def add_khata(name, amount, due_date, phone=""):
    with conn() as c:
        c.execute("INSERT INTO khata(merchant_id,name,amount,due_date,phone) VALUES(?,?,?,?,?)",
                  (mid(), _txt(name, "Customer name"), _num(amount, "Amount", 1), _date(due_date, "Due date"), phone_clean(phone)))


def khata_paid(kid):
    with conn() as c:
        c.execute("DELETE FROM khata WHERE id=? AND merchant_id=?", (int(kid), mid()))


def add_customer(name, every, last_visit, avg, phone=""):
    with conn() as c:
        c.execute("INSERT INTO customers(merchant_id,name,visit_every_days,last_visit,avg_bill,phone) VALUES(?,?,?,?,?,?)",
                  (mid(), _txt(name, "Customer name"), int(_num(every, "Visits every (days)", 1, 365)), _date(last_visit, "Last visit"), _num(avg, "Average bill"), phone_clean(phone)))


def customer_visit(cid):
    with conn() as c:
        c.execute("UPDATE customers SET last_visit=? WHERE id=? AND merchant_id=?", (today().isoformat(), int(cid), mid()))


# ---------- today's action plan: what the merchant approved or dismissed ----------
def plan_states(day):
    with conn() as c:
        return {r["key"]: r["status"] for r in c.execute("SELECT key, status FROM plan_state WHERE merchant_id=? AND day=?", (mid(), day))}


def set_plan_state(day, key, status):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO plan_state VALUES(?,?,?,?)", (mid(), day, key, status))


def clear_plan_dismissed(day):
    with conn() as c:
        c.execute("DELETE FROM plan_state WHERE merchant_id=? AND day=? AND status='dismissed'", (mid(), day))


# ---------- CSV import (replaces one table of this merchant, all or nothing) ----------
def import_csv(kind, raw):
    if kind not in SCHEMA:
        raise ValueError("Unknown file type: " + kind)
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    head = rows[0].keys() if rows else [h.strip() for h in text.splitlines()[0].split(",")]
    missing = [col for col in SCHEMA[kind] if col not in head]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))
    t, m = today(), mid()
    c = conn()
    try:
        if kind == "sales":
            c.execute("DELETE FROM sales WHERE merchant_id=?", (m,))
            for r in rows:
                c.execute("INSERT INTO sales(merchant_id,date,product_id,qty) VALUES(?,?,?,?)", (m, _date(r["date"], "date"), _txt(r["product_id"], "product_id"), int(_num(r["qty"], "qty"))))
        elif kind == "stock":
            c.execute("DELETE FROM products WHERE merchant_id=?", (m,))
            for r in rows:
                c.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?)", (m, _txt(r["product_id"], "product_id"), _txt(r["name_en"], "name_en"), r["name_hi"], r["name_mr"], _num(r["price"], "price"), _num(r["cost"], "cost"), _num(r["stock"], "stock"), int(_num(r["lead_days"], "lead_days", 0, 60)), _num(r["festival_uplift"], "festival_uplift", 0.5, 5)))
        elif kind == "khata":
            c.execute("DELETE FROM khata WHERE merchant_id=?", (m,))
            for r in rows:
                c.execute("INSERT INTO khata(merchant_id,name,amount,due_date,phone) VALUES(?,?,?,?,?)", (m, _txt(r["name"], "name"), _num(r["amount"], "amount"), (t - dt.timedelta(days=int(_num(r["days_overdue"], "days_overdue", -3650, 3650)))).isoformat(), phone_clean(r.get("phone"))))
        else:
            c.execute("DELETE FROM customers WHERE merchant_id=?", (m,))
            for r in rows:
                c.execute("INSERT INTO customers(merchant_id,name,visit_every_days,last_visit,avg_bill,phone) VALUES(?,?,?,?,?,?)", (m, _txt(r["name"], "name"), int(_num(r["visit_every_days"], "visit_every_days", 1, 365)), (t - dt.timedelta(days=int(_num(r["days_away"], "days_away", 0, 3650)))).isoformat(), _num(r["avg_bill"], "avg_bill"), phone_clean(r.get("phone"))))
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,'mode','mine')", (m,))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
