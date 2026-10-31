"""Run: python tests/test_auth.py   (temporary database; checks login and that merchants cannot see each other's data)"""
import datetime as dt, os, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
import jwt
from fastapi.testclient import TestClient
from app import auth, db
from app.main import app

c = TestClient(app)
def H(tok): return {"Authorization": "Bearer " + tok}
def reg(phone, shop, sample=False, pw="goodpass123"):
    return c.post("/api/auth/register", json={"phone": phone, "password": pw, "shop_name": shop, "owner_name": "Owner", "sample": sample})

# ---- register: validation, duplicate, stored safely
assert reg("12345", "x").status_code == 400                                              # bad mobile number
assert reg("9876543210", "x", pw="short").status_code == 400                             # short password
r = reg("98765 43210", "Sharma Kirana", sample=True); assert r.status_code == 200, r.text
A = r.json()["token"]; assert r.json()["merchant"]["shop_name"] == "Sharma Kirana"
assert reg("+91 9876543210", "again").status_code == 400                                 # same number, written differently
row = db.conn().execute("SELECT pw_hash, phone FROM merchants WHERE id=1").fetchone()
assert row["pw_hash"].startswith("scrypt$") and "goodpass123" not in row["pw_hash"] and row["phone"] == "919876543210"
print("register ok")

# ---- login: right / wrong / unknown number look the same, lockout after 5 wrong tries
assert c.post("/api/auth/login", json={"phone": "9876543210", "password": "goodpass123"}).status_code == 200
w1 = c.post("/api/auth/login", json={"phone": "9876543210", "password": "wrongpass1"})
w2 = c.post("/api/auth/login", json={"phone": "9123456780", "password": "wrongpass1"})
assert w1.status_code == w2.status_code == 401 and w1.json() == w2.json()
for _ in range(4): c.post("/api/auth/login", json={"phone": "9876543210", "password": "wrongpass1"})
assert c.post("/api/auth/login", json={"phone": "9876543210", "password": "goodpass123"}).status_code == 429   # locked, even with the right password
auth._fails.clear()
assert c.post("/api/auth/login", json={"phone": "9876543210", "password": "goodpass123"}).status_code == 200
print("login + lockout ok")

# ---- no token / bad token / tampered / expired: every data endpoint says 401
paths = [("get", "/api/data"), ("get", "/api/action-plan"), ("get", "/api/auth/me"), ("get", "/api/ai-status"), ("post", "/api/ask"), ("post", "/api/sale"),
         ("post", "/api/khata"), ("post", "/api/khata/1/paid"), ("post", "/api/customer"), ("post", "/api/customer/1/visit"), ("post", "/api/product"),
         ("post", "/api/sale/undo"), ("post", "/api/reset/empty"), ("post", "/api/reset/sample"), ("post", "/api/upload/khata"),
         ("post", "/api/action-plan/approve"), ("post", "/api/action-plan/dismiss"), ("post", "/api/action-plan/restore")]
exp = jwt.encode({"sub": "1", "exp": dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)}, auth._secret(), algorithm="HS256")
forged = jwt.encode({"sub": "1"}, "not-the-secret", algorithm="HS256")
for tok in (None, "garbage", A[:-3] + "xyz", exp, forged):
    for m, p in paths:
        hd = H(tok) if tok else {}
        assert getattr(c, m)(p, headers=hd).status_code == 401, (m, p, tok)
assert jwt.decode(forged, options={"verify_signature": False})["sub"] == "1"
none_alg = jwt.encode({"sub": "1"}, None, algorithm="none")
assert c.get("/api/data", headers=H(none_alg)).status_code == 401                         # "alg: none" trick refused
print("401 on all", len(paths), "protected endpoints ok")

# ---- isolation: merchant B (empty shop) cannot see or change merchant A (demo shop)
B = reg("9123456780", "Patil Stores").json()["token"]
a0 = c.get("/api/data", headers=H(A)).json(); b0 = c.get("/api/data", headers=H(B)).json()
assert len(a0["products"]) == 6 and a0["khata"] and b0["products"] == [] and b0["khata"] == [] and b0["lapsed"] == []
a_khata_id = a0["khata"][0]["id"]
# B tries to touch A's rows by id
c.post(f"/api/khata/{a_khata_id}/paid", headers=H(B))
c.post(f"/api/customer/{a0['lapsed'][0]['id']}/visit", headers=H(B))
assert c.post("/api/sale", json={"product_id": "atta", "qty": 1}, headers=H(B)).status_code == 400   # A's item is unknown to B
a1 = c.get("/api/data", headers=H(A)).json()
assert len(a1["khata"]) == len(a0["khata"]) and a1["lapsed"][0]["gone"] == a0["lapsed"][0]["gone"] and a1["products"][4]["stock"] == a0["products"][4]["stock"]
# B's plan and dismiss/approve cannot use A's actions
assert c.get("/api/action-plan", headers=H(B)).json()["actions"] == []
assert c.post("/api/action-plan/approve", json={"key": "khata:2"}, headers=H(B)).status_code == 400
assert c.post("/api/action-plan/dismiss", json={"key": "khata:2"}, headers=H(B)).status_code == 400
# B writes data, uploads CSV, resets: A is untouched
c.post("/api/product", json={"name_en": "Rice 1kg", "price": 60, "cost": 52, "stock": 10}, headers=H(B))
c.post("/api/khata", json={"name": "Only B", "amount": 99, "due_date": "2026-10-01"}, headers=H(B))
up = c.post("/api/upload/khata", files={"file": ("k.csv", b"name,amount,days_overdue\nB Customer,10,3\n")}, headers=H(B)); assert up.status_code == 200
c.post("/api/reset/empty", headers=H(B))
a2 = c.get("/api/data", headers=H(A)).json()
assert a2["products"] == a1["products"] and a2["khata"] == a1["khata"] and "Only B" not in str(a2) and "B Customer" not in str(a2) and "Rice" not in str(a2)
assert c.post("/api/upload/khata", files={"file": ("k.csv", b"x" * 2_100_000)}, headers=H(A)).status_code == 400   # too large
assert c.get("/api/data", headers=H(A)).json()["khata"] == a1["khata"]
print("isolation ok")

# ---- same requests at the same time from two merchants never mix
def who(i):
    t, own, other = (A, "Sunita Devi", "Only B") if i % 2 == 0 else (B, "Zed Only", "Sunita Devi")
    cl = TestClient(app); d = cl.get("/api/data", headers=H(t)).json(); s = str(d)
    return own in s and other not in s
c.post("/api/khata", json={"name": "Zed Only", "amount": 5, "due_date": "2026-10-01"}, headers=H(B))
with ThreadPoolExecutor(8) as ex:
    assert all(ex.map(who, range(40)))
print("concurrent requests ok")

# ---- WhatsApp link uses the customer's saved number
c.post("/api/khata", json={"name": "Raju", "amount": 5000, "due_date": "2026-09-01", "phone": "98765 11111"}, headers=H(A))
k = [x for x in c.get("/api/action-plan", headers=H(A)).json()["actions"] if x["kind"] == "khata"][0]
r = c.post("/api/action-plan/approve", json={"key": k["key"]}, headers=H(A)).json()
assert "Raju" in r["content"] and r["share_url"].startswith("https://wa.me/919876511111?text=") and r["sent"] is False
assert c.post("/api/khata", json={"name": "Bad", "amount": 5, "due_date": "2026-10-01", "phone": "12"}, headers=H(A)).status_code == 400
print("customer WhatsApp number ok")

# ---- me, language, demo accounts
assert c.get("/api/auth/me", headers=H(A)).json()["shop_name"] == "Sharma Kirana"
assert c.post("/api/auth/profile", json={"lang": "mr"}, headers=H(A)).status_code == 200 and c.get("/api/auth/me", headers=H(A)).json()["lang"] == "mr"
assert c.post("/api/auth/profile", json={"lang": "xx"}, headers=H(A)).status_code == 400
D = c.post("/api/auth/demo").json(); assert D["merchant"]["is_demo"] and len(c.get("/api/data", headers=H(D["token"])).json()["products"]) == 6
old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
db.conn().execute("UPDATE merchants SET created=? WHERE id=?", (old, D["merchant"]["id"])).connection.commit()
c.post("/api/auth/demo"); assert c.get("/api/data", headers=H(D["token"])).status_code == 401      # old guest shop removed, its token is dead
assert c.get("/api/health").status_code == 200
db.set_merchant(1)
db._mid.set(None)
try: db.conn(); db.mode(); raise SystemExit("should fail")
except PermissionError: print("no merchant set -> queries refused ok")
print("ALL AUTH TESTS OK")
