"""Merchant accounts: register, login, signed login tokens.
- Passwords are stored only as scrypt hashes (never the password itself).
- A login gives a signed token (JWT, 7 days). Every data endpoint needs it and only sees that merchant's rows.
- Too many wrong passwords lock that mobile number for 5 minutes (kept in memory, resets when the server restarts)."""
import datetime as dt
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

import jwt
from fastapi import Header, HTTPException

from . import db

TOKEN_DAYS = 7
MAX_FAILS, LOCK_SECONDS = 5, 300
_fails = {}  # phone -> [count, locked_until]
_DUMMY = None


def _secret():
    """JWT_SECRET from the environment; otherwise a random one is created once and kept next to the database."""
    env = os.getenv("JWT_SECRET")
    if env:
        return env
    f = Path(os.getenv("SAATHI_DB") or db.ROOT / "data" / "dukaan.db").parent / ".jwt_secret"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw, stored):
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


def make_token(merchant_id):
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(merchant_id), "iat": now, "exp": now + dt.timedelta(days=TOKEN_DAYS)}, _secret(), algorithm="HS256")


def _public(r):
    return {"id": r["id"], "shop_name": r["shop_name"], "owner_name": r["owner_name"], "lang": r["lang"] or "en", "is_demo": bool(r["is_demo"]),
            "phone_last4": (r["phone"] or "")[-4:]}


def get_merchant(merchant_id):
    with db.conn() as c:
        r = c.execute("SELECT * FROM merchants WHERE id=?", (int(merchant_id),)).fetchone()
    return _public(r) if r else None


def _session(merchant_id):
    return {"token": make_token(merchant_id), "merchant": get_merchant(merchant_id)}


def register(phone, password, shop_name, owner_name, sample=False):
    db.init()
    ph = db.phone_clean(phone)
    if not ph:
        raise ValueError("Mobile number is required")
    pw = str(password or "")
    if not 8 <= len(pw) <= 128:
        raise ValueError("Password must be 8 to 128 characters")
    shop, owner = db._txt(shop_name, "Shop name", 60), db._txt(owner_name, "Your name", 60)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM merchants WHERE phone=?", (ph,)).fetchone():
            raise ValueError("This mobile number is already registered. Please log in.")
        cur = c.execute("INSERT INTO merchants(phone,shop_name,owner_name,pw_hash,created) VALUES(?,?,?,?,?)",
                        (ph, shop, owner, hash_pw(pw), dt.datetime.now(dt.timezone.utc).isoformat()))
        mid = cur.lastrowid
    db.set_merchant(mid)
    db.seed_sample() if sample else db.reset("empty")
    return _session(mid)


def login(phone, password):
    db.init()
    try:
        ph = db.phone_clean(phone)
    except ValueError:
        ph = ""
    bad = HTTPException(401, "Wrong mobile number or password")
    fails = _fails.get(ph)
    if fails and fails[1] > time.time():
        raise HTTPException(429, "Too many wrong attempts. Please try again in a few minutes.")
    with db.conn() as c:
        r = c.execute("SELECT * FROM merchants WHERE phone=?", (ph,)).fetchone() if ph else None
    global _DUMMY
    _DUMMY = _DUMMY or hash_pw("dummy-password")
    ok = check_pw(str(password or ""), r["pw_hash"] if r else _DUMMY)  # same work whether or not the number exists
    if not (r and ok):
        f = _fails.setdefault(ph, [0, 0])
        f[0] += 1
        if f[0] >= MAX_FAILS:
            f[0], f[1] = 0, time.time() + LOCK_SECONDS
        raise bad
    _fails.pop(ph, None)
    return _session(r["id"])


def create_demo():
    """A fresh guest shop with sample data (for judges and first-time visitors). Guest shops are removed after a day."""
    db.init()
    _purge_old_demos()
    with db.conn() as c:
        cur = c.execute("INSERT INTO merchants(phone,shop_name,owner_name,pw_hash,is_demo,created) VALUES(NULL,?,?,?,1,?)",
                        ("Demo Kirana (sample data)", "Guest", "", dt.datetime.now(dt.timezone.utc).isoformat()))
        mid = cur.lastrowid
    db.set_merchant(mid)
    db.seed_sample()
    return _session(mid)


def _purge_old_demos():
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    with db.conn() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM merchants WHERE is_demo=1 AND created<?", (cut,))]
        for i in ids:
            for t in ("products", "sales", "khata", "customers", "meta", "plan_state"):
                c.execute(f"DELETE FROM {t} WHERE merchant_id=?", (i,))
            c.execute("DELETE FROM merchants WHERE id=?", (i,))


def set_lang(merchant_id, lang):
    if lang not in ("en", "hi", "mr"):
        raise ValueError("Language must be en, hi or mr")
    with db.conn() as c:
        c.execute("UPDATE merchants SET lang=? WHERE id=?", (lang, int(merchant_id)))


def merchant_from_token(token):
    try:
        data = jwt.decode(token, _secret(), algorithms=["HS256"])
        mid = int(data["sub"])
    except Exception:
        raise HTTPException(401, "Please log in again")
    if not get_merchant(mid):
        raise HTTPException(401, "Please log in again")
    return mid


async def current_merchant(authorization: str = Header(None)):
    """FastAPI dependency: checks the token and tells db.py which merchant this request belongs to.
    It is async on purpose so the merchant is visible to the sync endpoint that runs after it."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in")
    mid = merchant_from_token(authorization[7:].strip())
    db.set_merchant(mid)
    return mid
