"""Today's Business Action Plan.
Picks the 3 most useful things to do today from the saved shop data, using plain calculations (no AI needed).
Nothing is sent anywhere: approving an action only prepares text (order list / WhatsApp message) for the owner to copy or share."""
import urllib.parse

from . import db
from .data import build
from .tools import _items

LANGS = ("en", "hi", "mr")
RANK = {"high": 0, "medium": 1, "low": 2}


def inr(n):
    return "₹" + format(int(round(n)), ",d")


def _nm(names, lang):
    return names[{"en": 0, "hi": 1, "mr": 2}[lang]]


# ---------- wording (English / हिंदी / मराठी) ----------
TXT = {
    "restock": {
        "title": {"en": lambda q, n: f"Order {q} of {n} today", "hi": lambda q, n: f"आज {n} के {q} मँगवाइए", "mr": lambda q, n: f"आज {n} चे {q} मागवा"},
        "reason": {"en": lambda n, c, l: f"{n} stock lasts about {c} days but the supplier needs {l} days.",
                   "hi": lambda n, c, l: f"{n} का स्टॉक करीब {c} दिन चलेगा, पर सप्लायर को {l} दिन लगते हैं।",
                   "mr": lambda n, c, l: f"{n} चा साठा सुमारे {c} दिवस पुरेल, पण सप्लायरला {l} दिवस लागतात."},
        "benefit": {"en": lambda r: f"Avoids missing about {inr(r)} of sales (estimate).", "hi": lambda r: f"करीब {inr(r)} की बिक्री छूटने से बचेगी (अनुमान)।", "mr": lambda r: f"सुमारे {inr(r)} ची विक्री बुडण्यापासून वाचेल (अंदाज)."},
    },
    "khata": {
        "title": {"en": lambda n, a: f"Remind {n} about {inr(a)}", "hi": lambda n, a: f"{n} को {inr(a)} की याद दिलाइए", "mr": lambda n, a: f"{n} यांना {inr(a)} ची आठवण करा"},
        "reason": {"en": lambda n, d: f"Payment is {d} days overdue." if d > 0 else "Payment is due soon.",
                   "hi": lambda n, d: f"भुगतान {d} दिन से बाकी है।" if d > 0 else "भुगतान जल्दी देय है।",
                   "mr": lambda n, d: f"पेमेंट {d} दिवस उशिरा आहे." if d > 0 else "पेमेंट लवकरच देय आहे."},
        "benefit": {"en": lambda a: f"You may get back up to {inr(a)}.", "hi": lambda a: f"आपको {inr(a)} तक वापस मिल सकते हैं।", "mr": lambda a: f"तुम्हाला {inr(a)} पर्यंत परत मिळू शकतात."},
    },
    "winback": {
        "title": {"en": lambda n: f"Send {n} a special offer", "hi": lambda n: f"{n} को ख़ास ऑफ़र भेजिए", "mr": lambda n: f"{n} यांना खास ऑफर पाठवा"},
        "reason": {"en": lambda n, g, e: f"Usually visits every {e} days, but away {g} days.",
                   "hi": lambda n, g, e: f"आम तौर पर हर {e} दिन में आते हैं, पर {g} दिन से नहीं आए।",
                   "mr": lambda n, g, e: f"साधारणपणे दर {e} दिवसांनी येतात, पण {g} दिवस आले नाहीत."},
        "benefit": {"en": lambda a: f"One visit is worth about {inr(a)}.", "hi": lambda a: f"एक बार आने पर करीब {inr(a)} की बिक्री।", "mr": lambda a: f"एका भेटीत सुमारे {inr(a)} ची विक्री."},
    },
}
MSG = {
    "khata": {"en": lambda n, a: f"Namaste {n} ji, a gentle reminder from our shop: {inr(a)} is pending on your khata. You can pay anytime by UPI: <UPI pay link>. Thank you!",
              "hi": lambda n, a: f"नमस्ते {n} जी, दुकान की ओर से विनम्र याद: आपके खाते में {inr(a)} बाकी हैं। UPI से कभी भी भुगतान करें: <UPI pay link>। धन्यवाद!",
              "mr": lambda n, a: f"नमस्कार {n}, दुकानाकडून नम्र आठवण: तुमच्या खात्यावर {inr(a)} बाकी आहेत. UPI ने केव्हाही पेमेंट करा: <UPI pay link>. धन्यवाद!"},
    "winback": {"en": lambda n: f"Hi {n}, we miss you at the shop! Show this message this week for ₹20 off on ₹300 or more.",
                "hi": lambda n: f"नमस्ते {n}, दुकान पर आपकी याद आ रही है! इस हफ़्ते यह संदेश दिखाएँ और ₹300 की ख़रीद पर ₹20 की छूट पाएँ।",
                "mr": lambda n: f"नमस्कार {n}, दुकानात तुमची आठवण येते! या आठवड्यात हा संदेश दाखवा आणि ₹300 च्या खरेदीवर ₹20 सूट मिळवा."},
}
ORDER_HEAD = {"en": "Order list", "hi": "ऑर्डर सूची", "mr": "ऑर्डर यादी"}
NOTE = {
    "order_list": {"en": "Nothing has been ordered. Copy this list and send it to your distributor.",
                   "hi": "कुछ भी ऑर्डर नहीं हुआ है। यह सूची कॉपी करके अपने डिस्ट्रीब्यूटर को भेजें।",
                   "mr": "काहीही ऑर्डर झालेले नाही. ही यादी कॉपी करून तुमच्या डिस्ट्रीब्युटरला पाठवा."},
    "whatsapp": {"en": "Not sent. WhatsApp is not connected: copy the message or open WhatsApp and pick the customer yourself.",
                 "hi": "भेजा नहीं गया है। WhatsApp जुड़ा नहीं है: संदेश कॉपी करें या WhatsApp खोलकर ग्राहक ख़ुद चुनें।",
                 "mr": "पाठवलेले नाही. WhatsApp जोडलेले नाही: संदेश कॉपी करा किंवा WhatsApp उघडून ग्राहक स्वतः निवडा."},
}


def _candidates():
    """Every possible action today, each with a rupee 'score' used for ranking. Names kept in all 3 languages."""
    d, items = _items()
    out = []
    for i in items:
        p = i["p"]
        if i["status"] == "ok" or i["need"] <= 0:
            continue
        urgent = i["status"] == "order_today"
        gap = max(1.0, p["lead"] + 1 - i["cover"]) if urgent else 1.0
        risk = i["rate"] * p["price"] * gap
        out.append({"key": "restock:" + p["id"], "kind": "restock", "priority": "high" if urgent else "medium", "score": risk,
                    "qty": int(round(i["need"])), "amount_rs": round(risk), "names": p["n"], "cover": round(i["cover"], 1), "lead": p["lead"]})
    for k in d["khata"]:
        if k["od"] <= 0:
            continue
        out.append({"key": f"khata:{k['id']}", "kind": "khata", "priority": "high" if (k["od"] >= 7 or k["a"] >= 1000) else "medium",
                    "score": k["a"] * (1 + k["od"] / 30), "amount_rs": round(k["a"]), "name": k["n"], "od": k["od"], "phone": k["ph"]})
    for c in d["lapsed"]:
        out.append({"key": f"winback:{c['id']}", "kind": "winback", "priority": "medium" if c["avg"] >= 400 else "low",
                    "score": c["avg"] * min(c["gone"] / max(c["every"], 1), 5) / 2, "amount_rs": round(c["avg"]), "name": c["n"], "gone": c["gone"], "every": c["every"], "phone": c["ph"]})
    return d, items, out


def _pick(cands, n=3):
    """Best action of each kind first (so the plan covers stock, money and customers), then the best of the rest."""
    best = {}
    for c in sorted(cands, key=lambda c: -c["score"]):
        best.setdefault(c["kind"], c)
    chosen = list(best.values())
    rest = [c for c in sorted(cands, key=lambda c: -c["score"]) if c not in chosen]
    chosen = sorted(chosen, key=lambda c: -c["score"])[:n]
    chosen += rest[: n - len(chosen)]
    return sorted(chosen, key=lambda c: (RANK[c["priority"]], -c["score"]))


def _present(c, lang, status):
    t = TXT[c["kind"]]
    if c["kind"] == "restock":
        nm = _nm(c["names"], lang)
        title, reason, benefit = t["title"][lang](c["qty"], nm), t["reason"][lang](nm, c["cover"], c["lead"]), t["benefit"][lang](c["amount_rs"])
    elif c["kind"] == "khata":
        title, reason, benefit = t["title"][lang](c["name"], c["amount_rs"]), t["reason"][lang](c["name"], c["od"]), t["benefit"][lang](c["amount_rs"])
    else:
        title, reason, benefit = t["title"][lang](c["name"]), t["reason"][lang](c["name"], c["gone"], c["every"]), t["benefit"][lang](c["amount_rs"])
    return {"key": c["key"], "kind": c["kind"], "priority": c["priority"], "status": status, "title": title, "reason": reason,
            "benefit": benefit, "amount_rs": c["amount_rs"], "qty": c.get("qty")}


def _lang(lang):
    return lang if lang in LANGS else "en"


def get_plan(lang="en"):
    lang = _lang(lang)
    d, _, cands = _candidates()
    day = d["asOf"]
    states = db.plan_states(day)
    live = [c for c in cands if states.get(c["key"]) != "dismissed"]
    acts = [_present(c, lang, states.get(c["key"], "pending")) for c in _pick(live)]
    return {"date": day, "actions": acts, "dismissed_today": sum(1 for v in states.values() if v == "dismissed"),
            "all_done": bool(acts) and all(a["status"] == "approved" for a in acts), "has_data": bool(d["products"] or d["khata"] or d["lapsed"])}


def _find(key):
    d, items, cands = _candidates()
    c = next((c for c in cands if c["key"] == key), None)
    if not c:
        raise ValueError("This action is no longer in today's plan")
    return d["asOf"], items, c


def dismiss(key):
    day, _, c = _find(key)
    db.set_plan_state(day, c["key"], "dismissed")


def restore():
    db.clear_plan_dismissed(db.today().isoformat())


def approve(key, lang="en"):
    """Marks the action approved and returns the text the owner can copy or share. Does NOT send anything."""
    lang = _lang(lang)
    day, items, c = _find(key)
    if c["kind"] == "restock":
        rows = [i for i in items if i["need"] > 0]
        rows.sort(key=lambda i: i["cover"])
        lines = [f"- {i['p']['n'][0]}" + (f" ({_nm(i['p']['n'], lang)})" if lang != "en" else "") + f": {int(round(i['need']))}" for i in rows]
        content = f"{ORDER_HEAD[lang]} ({day}):\n" + "\n".join(lines) + f"\n\n{'Est. cost' if lang == 'en' else 'अनुमानित लागत' if lang == 'hi' else 'अंदाजे खर्च'}: {inr(sum(i['need'] * i['p']['cost'] for i in rows))}"
        kind, title = "order_list", ORDER_HEAD[lang]
    elif c["kind"] == "khata":
        content, kind, title = MSG["khata"][lang](c["name"], c["amount_rs"]), "whatsapp", c["name"]
    else:
        content, kind, title = MSG["winback"][lang](c["name"]), "whatsapp", c["name"]
    db.set_plan_state(day, c["key"], "approved")
    out = {"key": c["key"], "kind": kind, "title": title, "content": content, "sent": False, "note": NOTE["order_list" if kind == "order_list" else "whatsapp"][lang]}
    # With a saved number the chat for that customer opens; otherwise the owner picks the contact in WhatsApp. Never sent automatically.
    out["share_url"] = "https://wa.me/" + (c.get("phone") or "") + "?text=" + urllib.parse.quote(content)
    return out
