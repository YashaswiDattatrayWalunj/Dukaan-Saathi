"""Run: python tests/test_plan.py   (temporary database; your real data is not touched)"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
assert c.get("/api/action-plan").status_code == 401            # no login, no data
c.headers["Authorization"] = "Bearer " + c.post("/api/auth/demo").json()["token"]
p = c.get("/api/action-plan").json()
kinds = [a["kind"] for a in p["actions"]]
assert len(p["actions"]) == 3 and sorted(kinds) == ["khata", "restock", "winback"], kinds   # covers stock, money, customers
assert p["actions"][0]["priority"] == "high" and all(a["status"] == "pending" for a in p["actions"])
assert any(a["key"] == "khata:2" and "1,250" in a["title"] for a in p["actions"])             # Meena Tai, Rs 1,250
assert all(isinstance(a["qty"], int) for a in p["actions"] if a["kind"] == "restock")
print("plan ok:", [a["title"] for a in p["actions"]])
# three languages
for lang, word in (("hi", "आज"), ("mr", "आज")):
    assert word in c.get("/api/action-plan?lang=" + lang).json()["actions"][0]["title"]
assert c.get("/api/action-plan?lang=xx").json()["actions"][0]["title"].startswith("Order")   # unknown language -> English
# approve: returns text, sends nothing
r = c.post("/api/action-plan/approve", json={"key": "khata:2", "lang": "en"}).json()
assert r["sent"] is False and "Meena Tai" in r["content"] and "₹1,250" in r["content"] and r["share_url"].startswith("https://wa.me/?text=") and "Not sent" in r["note"]
r = c.post("/api/action-plan/approve", json={"key": "restock:atta", "lang": "hi"}).json()
assert r["kind"] == "order_list" and "Atta 5kg" in r["content"] and "आटा" in r["content"]
st = {a["key"]: a["status"] for a in c.get("/api/action-plan").json()["actions"]}
assert st["khata:2"] == "approved" and st["restock:atta"] == "approved"
# dismiss: replaced by the next best action, can be restored
r = c.post("/api/action-plan/dismiss", json={"key": "winback:3"}); assert r.status_code == 200
p = c.get("/api/action-plan").json()
assert "winback:3" not in [a["key"] for a in p["actions"]] and len(p["actions"]) == 3 and p["dismissed_today"] == 1
c.post("/api/action-plan/restore"); assert "winback:3" in [a["key"] for a in c.get("/api/action-plan").json()["actions"]]
# bad input
assert c.post("/api/action-plan/approve", json={"key": "nope"}).status_code == 400
assert c.post("/api/action-plan/dismiss", json={"key": "khata:999"}).status_code == 400
assert c.post("/api/action-plan/approve", json={}).status_code == 422
# plan reacts to the data: paying khata removes that action; empty shop gives an empty plan with a hint
c.post("/api/khata/2/paid"); assert "khata:2" not in [a["key"] for a in c.get("/api/action-plan").json()["actions"]]
c.post("/api/reset/empty"); p = c.get("/api/action-plan").json(); assert p["actions"] == [] and p["has_data"] is False
c.post("/api/product", json={"name_en": "Rice 1kg", "price": 60, "cost": 52, "stock": 100, "lead_days": 2}); c.post("/api/sale", json={"product_id": "rice_1kg", "qty": 1})
assert c.get("/api/action-plan").json()["actions"] == []                                     # plenty of stock, nothing urgent
c.post("/api/reset/sample"); assert len(c.get("/api/action-plan").json()["actions"]) == 3 and c.get("/api/action-plan").json()["dismissed_today"] == 0
print("ALL PLAN TESTS OK")
