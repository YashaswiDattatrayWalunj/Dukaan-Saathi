"""Run: python tests/test_tools.py   (checks the numbers the AI will be given)"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
from app import auth as _a, db as _d; _d.init(); _d.set_merchant(_a.register("9876543210", "password1", "Test Store", "Owner", sample=True)["merchant"]["id"])
from app import tools

s = tools.sales_summary(); print(s)
assert s["today_sales_rs"] > 0 and s["last_7_days_profit_rs"] < s["last_7_days_sales_rs"]
print(tools.top_items("week"))
r = tools.restock_list(); print([(i["name"], i["days_of_stock_left"], i["order_qty"], i["status"]) for i in r["items"]])
assert r["items"][0]["days_of_stock_left"] <= r["items"][-1]["days_of_stock_left"]
k = tools.khata_list(); print(k)
assert "Sunita" not in str(k), "names must be masked"
assert "Sunita Devi" in tools.unmask("Remind Customer K1 today")
assert "Priya Nair" not in str(tools.lapsed_customers())
print("ALL OK")
