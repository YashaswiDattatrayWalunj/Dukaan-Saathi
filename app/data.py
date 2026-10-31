"""Builds what the dashboard and the AI tools need from the saved shop data (see db.py)."""
import datetime as dt

from . import db
from .db import SCHEMA


def build():
    db.ensure()
    t = db.today()
    days = [t - dt.timedelta(days=13 - i) for i in range(14)]
    idx = {d.isoformat(): i for i, d in enumerate(days)}
    with db.conn() as c:
        m = db.mid()
        prods = c.execute("SELECT * FROM products WHERE merchant_id=? ORDER BY rowid", (m,)).fetchall()
        q = {p["id"]: [0] * 14 for p in prods}
        for r in c.execute("SELECT date, product_id, SUM(qty) s FROM sales WHERE merchant_id=? AND date>=? AND date<=? GROUP BY date, product_id", (m, days[0].isoformat(), t.isoformat())):
            if r["product_id"] in q and r["date"] in idx:
                q[r["product_id"]][idx[r["date"]]] = int(r["s"])
        khata = c.execute("SELECT * FROM khata WHERE merchant_id=?", (m,)).fetchall()
        custs = c.execute("SELECT * FROM customers WHERE merchant_id=?", (m,)).fetchall()
    products = [{"id": p["id"], "n": [p["name_en"], p["name_hi"] or p["name_en"], p["name_mr"] or p["name_hi"] or p["name_en"]],
                 "price": p["price"], "cost": p["cost"], "stock": p["stock"], "lead": p["lead_days"],
                 "fest": p["festival_uplift"], "q": q[p["id"]]} for p in prods]
    kh = sorted(({"id": k["id"], "n": k["name"], "a": k["amount"], "od": (t - dt.date.fromisoformat(k["due_date"])).days, "ph": k["phone"] or ""} for k in khata), key=lambda k: -k["od"])
    lapsed = []
    for cu in custs:
        gone = (t - dt.date.fromisoformat(cu["last_visit"])).days
        if gone > 2 * cu["visit_every_days"]:  # away for more than twice their usual gap
            lapsed.append({"id": cu["id"], "n": cu["name"], "every": cu["visit_every_days"], "gone": gone, "avg": cu["avg_bill"], "ph": cu["phone"] or ""})
    lapsed.sort(key=lambda x: -x["gone"])
    return {"asOf": t.isoformat(), "mode": db.mode(), "products": products, "khata": kh, "lapsed": lapsed}


def save_upload(kind, raw):
    try:
        db.import_csv(kind, raw)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"File could not be read ({e}). Old data kept.")
