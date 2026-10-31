"""Business calculations. The AI can only get numbers by calling these functions.
Customer names are masked ("Customer K1") before the AI sees them and restored in the final answer."""
import math

from .data import build


def _items(boost=True):
    d = build()
    out = []
    for p in d["products"]:
        q = p["q"]
        avg7 = sum(q[7:]) / 7
        rate = avg7 * (p["fest"] if boost else 1)
        cover = p["stock"] / rate if rate else 99
        need = max(0, math.ceil(rate * (p["lead"] + 4)) - p["stock"])
        status = "order_today" if cover <= p["lead"] else "order_soon" if cover <= p["lead"] + 3 else "ok"
        out.append({"p": p, "rate": rate, "cover": cover, "need": need, "status": status})
    return d, out


def _names(p):
    return {"name": p["n"][0], "name_hi": p["n"][1], "name_mr": p["n"][2]}


def sales_summary():
    """Today's and yesterday's sales, week sales and week profit."""
    d, items = _items()
    td = sum(i["p"]["q"][13] * i["p"]["price"] for i in items)
    yd = sum(i["p"]["q"][12] * i["p"]["price"] for i in items)
    wk = sum(sum(i["p"]["q"][7:]) * i["p"]["price"] for i in items)
    pr = sum(sum(i["p"]["q"][7:]) * (i["p"]["price"] - i["p"]["cost"]) for i in items)
    units = sum(i["p"]["q"][13] for i in items)
    return {"date": d["asOf"], "today_sales_rs": round(td), "yesterday_sales_rs": round(yd),
            "change_vs_yesterday_pct": round((td - yd) / yd * 100) if yd else None,
            "bills_today_estimated": round(units / 2.8), "last_7_days_sales_rs": round(wk),
            "last_7_days_profit_rs": round(pr),
            "profit_note": "sale price minus item cost; shop rent, wages and other expenses not included"}


def top_items(period="today", limit=3):
    """Best-selling items by sales value for period 'today' or 'week'."""
    _, items = _items()
    sl = slice(13, 14) if period == "today" else slice(7, 14)
    rows = [{**_names(i["p"]), "units": sum(i["p"]["q"][sl]), "sales_rs": round(sum(i["p"]["q"][sl]) * i["p"]["price"])} for i in items]
    return {"period": period, "items": sorted(rows, key=lambda r: -r["sales_rs"])[: int(limit)]}


def restock_list(diwali_boost=True):
    """Stock check: days of stock left, supplier lead time, how many to order. Urgent first."""
    _, items = _items(diwali_boost)
    rows = [{**_names(i["p"]), "stock": i["p"]["stock"], "sells_per_day": round(i["rate"], 1),
             "days_of_stock_left": round(i["cover"], 1), "supplier_lead_days": i["p"]["lead"],
             "order_qty": i["need"], "status": i["status"]} for i in items]
    return {"diwali_boost_applied": diwali_boost, "items": sorted(rows, key=lambda r: r["days_of_stock_left"])}


def _km():
    return {f"Customer K{i+1}": k["n"] for i, k in enumerate(build()["khata"])}


def _lm():
    return {f"Customer R{i+1}": c["n"] for i, c in enumerate(build()["lapsed"])}


def khata_list():
    """Pending udhaar per customer (names masked)."""
    rows = [{"customer": f"Customer K{i+1}", "amount_rs": round(k["a"]), "days_overdue": k["od"]} for i, k in enumerate(build()["khata"])]
    return {"total_pending_rs": sum(r["amount_rs"] for r in rows), "customers": rows}


def lapsed_customers():
    """Regular customers who stopped visiting (names masked)."""
    rows = [{"customer": f"Customer R{i+1}", "usually_visits_every_days": c["every"], "days_away": c["gone"],
             "average_bill_rs": round(c["avg"])} for i, c in enumerate(build()["lapsed"])]
    return {"customers": rows}


FUNCS = {"sales_summary": sales_summary, "top_items": top_items, "restock_list": restock_list,
         "khata_list": khata_list, "lapsed_customers": lapsed_customers}


def unmask(text):
    m = {**_km(), **_lm()}
    for label in sorted(m, key=len, reverse=True):
        text = text.replace(label, m[label])
    return text
