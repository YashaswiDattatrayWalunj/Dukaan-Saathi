"""Conservative CSV import for merchant-exported payment/settlement reports.
Never calls undocumented Paytm endpoints. Column names are mapped from common report headers;
merchant must review the preview before committing.
"""
import csv, datetime as dt, io, json
from . import db

ALIASES = {
 "source_transaction_id": ["transaction id","txn id","transaction_id","txn_id","payment id","payment_id","reference id","reference_id","txn reference id"],
 "txn_date": ["date","transaction date","txn date","transaction_date","txn_date","created at","created_at","payment date"],
 "amount": ["amount","transaction amount","txn amount","transaction_amount","txn_amount","gross amount"],
 "status": ["status","transaction status","txn status","payment status","transaction_status"],
 "order_id": ["order id","order_id","merchant order id","merchant_order_id"],
 "payment_mode": ["payment mode","payment_mode","mode","instrument"],
 "txn_type": ["type","transaction type","txn type","transaction_type"],
}
def _norm(s): return " ".join(str(s or "").strip().lower().replace("_"," ").replace("-"," ").split())
def _pick(headers, key):
    normalized = {_norm(h): h for h in headers}
    for alias in ALIASES[key]:
        if _norm(alias) in normalized: return normalized[_norm(alias)]
    return None
def _date(value):
    v = str(value or "").strip()
    for fmt in (None, "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return (dt.date.fromisoformat(v[:10]) if fmt is None else dt.datetime.strptime(v,fmt).date()).isoformat()
        except ValueError: pass
    raise ValueError("Date must be recognizable (for example 2026-10-31 or 31/10/2026)")
def parse(raw):
    try: text=raw.decode("utf-8-sig")
    except UnicodeDecodeError: raise ValueError("CSV must be UTF-8 encoded")
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames: raise ValueError("CSV has no header row")
    cols={k:_pick(reader.fieldnames,k) for k in ("source_transaction_id","txn_date","amount","status","order_id","payment_mode","txn_type")}
    missing=[k for k in ("source_transaction_id","txn_date","amount","status") if not cols[k]]
    if missing: raise ValueError("Could not map required columns: "+", ".join(missing)+". Include transaction ID, date, amount and status.")
    rows=[]; errors=[]; seen=set()
    for line,row in enumerate(reader,2):
        try:
            tid=str(row.get(cols["source_transaction_id"]) or "").strip()
            if not tid: raise ValueError("transaction ID is empty")
            if tid in seen: raise ValueError("duplicate transaction ID in this file")
            seen.add(tid)
            amount=float(str(row.get(cols["amount"]) or "").replace(",","").replace("₹","").strip())
            if amount < 0 or amount > 100_000_000: raise ValueError("amount must be between 0 and 100,000,000")
            status=str(row.get(cols["status"]) or "").strip().lower()
            if not status: raise ValueError("status is empty")
            date=_date(row.get(cols["txn_date"]))
            rows.append({"source_transaction_id":tid,"txn_date":date,"amount":round(amount,2),"status":status,
                "order_id":str(row.get(cols["order_id"]) or "").strip() if cols["order_id"] else "",
                "payment_mode":str(row.get(cols["payment_mode"]) or "").strip() if cols["payment_mode"] else "",
                "txn_type":str(row.get(cols["txn_type"]) or "payment").strip().lower() if cols["txn_type"] else "payment",
                "source_row":line})
        except Exception as e: errors.append({"row":line,"error":str(e)})
    if not rows and errors: raise ValueError("No valid transactions found. First error: row "+str(errors[0]["row"])+": "+errors[0]["error"])
    return {"columns_mapped":{k:v for k,v in cols.items() if v}, "valid_count":len(rows),"errors":errors,"rows":rows}
def commit(rows):
    if not isinstance(rows,list) or len(rows)>10000: raise ValueError("Rows must be a list of up to 10,000 previewed transactions")
    m=db.mid(); inserted=0; duplicates=0
    with db.conn() as c:
        for row in rows:
            tid=str(row.get("source_transaction_id") or "").strip()
            if not tid: raise ValueError("Transaction ID is required")
            date=_date(row.get("txn_date"))
            try: amount=float(row.get("amount"))
            except (TypeError,ValueError): raise ValueError("Amount must be numeric")
            if amount<0 or amount>100_000_000: raise ValueError("Amount is out of range")
            status=str(row.get("status") or "").strip().lower()
            if not status: raise ValueError("Status is required")
            cur=c.execute("""INSERT OR IGNORE INTO paytm_transactions
                (merchant_id,source_transaction_id,txn_date,amount,status,order_id,payment_mode,txn_type,raw_json,imported_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",(m,tid,date,round(amount,2),status,str(row.get("order_id") or "")[:120],
                str(row.get("payment_mode") or "")[:80],str(row.get("txn_type") or "payment")[:40],
                json.dumps(row,ensure_ascii=False),dt.datetime.now(dt.timezone.utc).isoformat()))
            if cur.rowcount: inserted+=1
            else: duplicates+=1
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,'paytm_import_mode','imported_report')",(m,))
    return {"ok":True,"inserted":inserted,"duplicates_skipped":duplicates,"source":"imported merchant report"}
def summary():
    m=db.mid()
    with db.conn() as c:
        rows=c.execute("SELECT status, COUNT(*) n, COALESCE(SUM(amount),0) total FROM paytm_transactions WHERE merchant_id=? GROUP BY status",(m,)).fetchall()
        total=c.execute("SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN lower(status) IN ('success','successful','captured','settled','completed') THEN amount ELSE 0 END),0) collected FROM paytm_transactions WHERE merchant_id=?",(m,)).fetchone()
        recent=c.execute("SELECT source_transaction_id,txn_date,amount,status,order_id,payment_mode,txn_type FROM paytm_transactions WHERE merchant_id=? ORDER BY txn_date DESC,id DESC LIMIT 100",(m,)).fetchall()
    return {"source":"imported merchant report","transaction_count":total["n"],"successful_collections_rs":round(total["collected"],2),
            "status_breakdown":[dict(r) for r in rows],"transactions":[dict(r) for r in recent]}
