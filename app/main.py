from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from . import ai, auth, db, plan, paytm_import
from .data import SCHEMA, build, save_upload

db.init()
app = FastAPI(title="Dukaan Saathi", description="AI business partner for Paytm merchants (prototype)")


class RegisterIn(BaseModel):
    phone: str
    password: str
    shop_name: str
    owner_name: str
    sample: bool = False


class LoginIn(BaseModel):
    phone: str
    password: str


class ProfileIn(BaseModel):
    lang: str


class AskIn(BaseModel):
    question: str
    lang: str = "en"


class PlanIn(BaseModel):
    key: str
    lang: str = "en"


class ProductIn(BaseModel):
    name_en: str
    name_hi: str = ""
    name_mr: str = ""
    price: float
    cost: float
    stock: float
    lead_days: int = 2
    festival_uplift: float = 1.1


class SaleIn(BaseModel):
    product_id: str
    qty: int = 1
    date: Optional[str] = None


class KhataIn(BaseModel):
    name: str
    amount: float
    due_date: str
    phone: str = ""


class PaytmImportCommitIn(BaseModel):
    rows: list[dict]


class CustomerIn(BaseModel):
    name: str
    visit_every_days: int
    last_visit: str
    avg_bill: float
    phone: str = ""


def run(fn, *a):
    try:
        return fn(*a) or {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/auth/register")
def auth_register(b: RegisterIn):
    return run(auth.register, b.phone, b.password, b.shop_name, b.owner_name, b.sample)


@app.post("/api/auth/login")
def auth_login(b: LoginIn):
    return auth.login(b.phone, b.password)


@app.post("/api/auth/demo")
def auth_demo():
    return auth.create_demo()


@app.get("/api/auth/me")
def auth_me(m: int = Depends(auth.current_merchant)):
    return auth.get_merchant(m)


@app.post("/api/auth/profile")
def auth_profile(b: ProfileIn, m: int = Depends(auth.current_merchant)):
    return run(auth.set_lang, m, b.lang)


@app.get("/api/ai-status", dependencies=[Depends(auth.current_merchant)])
def ai_status():
    return ai.status()


@app.post("/api/ask", dependencies=[Depends(auth.current_merchant)])
def ask(body: AskIn):
    """Returns {"answer": null} when the AI is unavailable, so the page falls back to its rule-based answers."""
    try:
        answer, used = ai.ask(body.question[:500], body.lang if body.lang in ("en", "hi", "mr") else "en")
        return {"answer": answer, "tools": used}
    except Exception as e:
        print("AI unavailable:", repr(e))
        return {"answer": None, "tools": [], "error": str(e)[:200]}


def _lang(l):
    return l if l in ("en", "hi", "mr") else "en"


@app.get("/api/action-plan", dependencies=[Depends(auth.current_merchant)])
def action_plan(lang: str = "en"):
    """Top 3 things to do today, ranked by calculation (no AI needed)."""
    return plan.get_plan(_lang(lang))


@app.post("/api/action-plan/approve", dependencies=[Depends(auth.current_merchant)])
def action_plan_approve(b: PlanIn):
    """Prepares the order list or message. Nothing is sent: the owner copies or shares it."""
    return run(plan.approve, b.key, _lang(b.lang))


@app.post("/api/action-plan/dismiss", dependencies=[Depends(auth.current_merchant)])
def action_plan_dismiss(b: PlanIn):
    return run(plan.dismiss, b.key)


@app.post("/api/action-plan/restore", dependencies=[Depends(auth.current_merchant)])
def action_plan_restore():
    return run(plan.restore)


@app.get("/api/data", dependencies=[Depends(auth.current_merchant)])
def data():
    return build()


@app.post("/api/product", dependencies=[Depends(auth.current_merchant)])
def product(b: ProductIn):
    return run(lambda: {"ok": True, "id": db.upsert_product(b.dict())})


@app.post("/api/sale", dependencies=[Depends(auth.current_merchant)])
def sale(b: SaleIn):
    return run(db.record_sale, b.product_id, b.qty, b.date)


@app.post("/api/sale/undo", dependencies=[Depends(auth.current_merchant)])
def sale_undo():
    return {"ok": True, "undone": db.undo_sale()}


@app.post("/api/khata", dependencies=[Depends(auth.current_merchant)])
def khata(b: KhataIn):
    return run(db.add_khata, b.name, b.amount, b.due_date, b.phone)


@app.post("/api/khata/{kid}/paid", dependencies=[Depends(auth.current_merchant)])
def khata_paid(kid: int):
    return run(db.khata_paid, kid)


@app.post("/api/customer", dependencies=[Depends(auth.current_merchant)])
def customer(b: CustomerIn):
    return run(db.add_customer, b.name, b.visit_every_days, b.last_visit, b.avg_bill, b.phone)


@app.post("/api/customer/{cid}/visit", dependencies=[Depends(auth.current_merchant)])
def customer_visit(cid: int):
    return run(db.customer_visit, cid)


@app.post("/api/reset/{kind}", dependencies=[Depends(auth.current_merchant)])
def reset(kind: str):
    return run(db.reset, kind)



@app.post("/api/integrations/paytm/preview", dependencies=[Depends(auth.current_merchant)])
async def paytm_csv_preview(file: UploadFile = File(...)):
    """Preview a merchant-exported Paytm CSV; does not save transactions."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV report")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(400, "File is too large (limit 2 MB)")
    try:
        return paytm_import.parse(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/integrations/paytm/confirm", dependencies=[Depends(auth.current_merchant)])
def paytm_csv_confirm(body: PaytmImportCommitIn):
    """Persist rows reviewed in the preview. Existing source transaction IDs are skipped."""
    return run(paytm_import.commit, body.rows)


@app.get("/api/integrations/paytm/summary", dependencies=[Depends(auth.current_merchant)])
def paytm_summary():
    return paytm_import.summary()


@app.get("/api/schema")
def schema():
    return SCHEMA


@app.post("/api/upload/{kind}", dependencies=[Depends(auth.current_merchant)])
async def upload(kind: str, file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(400, "File is too large (limit 2 MB)")
    try:
        save_upload(kind, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "kind": kind}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
