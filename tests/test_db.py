"""Run: python tests/test_db.py   (uses a temporary database, your real data is not touched)"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
from app import auth as _a, db as _d; _d.init(); _d.set_merchant(_a.register("9876543210", "password1", "Test Store", "Owner", sample=True)["merchant"]["id"])
from app import db, tools
from app.data import build, save_upload
db.init()
d = build(); assert d["mode"] == "sample" and len(d["products"]) == 6 and d["asOf"] == "2026-10-31"
print("sample ok:", [p["id"] for p in d["products"]], "lapsed:", [x["n"] for x in d["lapsed"]])
# my own shop
db.reset("empty"); d = build(); assert d["mode"] == "mine" and d["products"] == []
print(tools.sales_summary()["today_sales_rs"], tools.restock_list()["items"], tools.khata_list()["total_pending_rs"])
pid = db.upsert_product({"name_en": "Rice 1kg", "name_hi": "चावल 1kg", "price": 60, "cost": 52, "stock": 10, "lead_days": 2})
assert pid == "rice_1kg"
db.record_sale(pid, 3); db.record_sale(pid, 2)
p = build()["products"][0]; assert p["stock"] == 5 and p["q"][13] == 5, p
db.undo_sale(); p = build()["products"][0]; assert p["stock"] == 7 and p["q"][13] == 3, p
db.record_sale(pid, 20); assert build()["products"][0]["stock"] == 0           # stock never goes negative
db.undo_sale(); assert build()["products"][0]["stock"] == 7                    # undo gives back only what was taken
for bad in (lambda: db.record_sale("nope", 1), lambda: db.upsert_product({"name_en": "x", "price": "abc", "cost": 1, "stock": 1}),
            lambda: db.add_khata("A", 100, "31-10-2026"), lambda: db.record_sale(pid, 0)):
    try: bad(); raise SystemExit("should have failed")
    except ValueError as e: print("rejected:", e)
db.add_khata("Ramesh", 400, "2026-10-20"); k = build()["khata"][0]; assert k["od"] == 11 and k["n"] == "Ramesh"
db.khata_paid(k["id"]); assert build()["khata"] == []
db.add_customer("Asha", 7, "2026-10-01", 300); l = build()["lapsed"]; assert l and l[0]["gone"] == 30
db.customer_visit(l[0]["id"]); assert build()["lapsed"] == []
# csv upload: good, bad (rolled back)
save_upload("khata", b"name,amount,days_overdue\nZoya,250,5\n"); assert build()["khata"][0]["n"] == "Zoya"
try: save_upload("khata", b"name,amount,days_overdue\nBad,abc,5\n"); raise SystemExit("should fail")
except ValueError as e: print("bad csv rejected:", e)
assert build()["khata"][0]["n"] == "Zoya"                                       # old data kept
try: save_upload("sales", b"date,qty\n"); raise SystemExit("should fail")
except ValueError as e: print("missing columns:", e)
db.reset("sample"); assert build()["mode"] == "sample" and len(build()["products"]) == 6
print("ALL DB TESTS OK")
