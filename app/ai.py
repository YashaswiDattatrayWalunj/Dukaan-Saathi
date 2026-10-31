"""Ask Anything with a real LLM. Python calculates (tools.py); the AI only chooses a tool and explains the result."""
import json
import os

from . import tools

SYSTEM = """You are Dukaan Saathi, a business helper for a small kirana shop owner in India.
Rules:
- Every number must come from a tool result. Call a tool first; never guess or invent figures.
- If the tools do not have the data needed (weather, competitors, GST, anything else), say clearly that you do not have that data.
- Reply in the language of the user's question (English, Hindi or Marathi; use Devanagari for Hindi and Marathi). The 'lang' hint is the app's selected language.
- Keep it short: 2 or 3 simple sentences, rupee amounts like ₹1,200. Use the item's name in the reply language (name_hi / name_mr) when available.
- When useful, end with one clear next action (for example what to order, or who to remind).
- Profit means sale price minus item cost and ignores shop expenses; say so when giving profit.
- You cannot send messages, approve loans or place orders. Only suggest them.
- Customer names appear as labels like 'Customer K1'. Use the labels exactly as given."""

NOARGS = {"type": "object", "properties": {}}
TOOLS = [
    {"name": "sales_summary", "description": "Today's sales, yesterday's sales, change %, estimated bills, last 7 days sales and profit.", "input_schema": NOARGS},
    {"name": "top_items", "description": "Best-selling items by sales value.", "input_schema": {"type": "object", "properties": {"period": {"type": "string", "enum": ["today", "week"]}, "limit": {"type": "integer"}}}},
    {"name": "restock_list", "description": "Stock left in days, supplier lead time and how many units to order for each item, urgent first.", "input_schema": {"type": "object", "properties": {"diwali_boost": {"type": "boolean", "description": "Add expected Diwali demand. Default true."}}}},
    {"name": "khata_list", "description": "Pending udhaar (credit) per customer with days overdue.", "input_schema": NOARGS},
    {"name": "lapsed_customers", "description": "Regular customers who stopped visiting, with usual visit gap and average bill.", "input_schema": NOARGS},
]


def provider():
    p = os.getenv("AI_PROVIDER", "").lower()
    if p in ("claude", "gemini", "sarvam"):
        return p
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("SARVAM_API_KEY"):
        return "sarvam"
    return None


def status():
    p = provider()
    model = {"gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "sarvam": os.getenv("SARVAM_MODEL", "sarvam-105b")}.get(p) or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    return {"configured": p is not None, "provider": p, "model": model if p else None}


def ask(question, lang="en"):
    p = provider()
    if p == "gemini":
        return ask_gemini(question, lang)
    if p == "sarvam":
        return ask_sarvam(question, lang)
    if p == "claude":
        return ask_claude(question, lang)
    raise RuntimeError("No AI key set (SARVAM_API_KEY, GEMINI_API_KEY or ANTHROPIC_API_KEY)")


def _sarvam_post(body, key):
    import urllib.request
    req = urllib.request.Request("https://api.sarvam.ai/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "api-subscription-key": key,
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def ask_sarvam(question, lang="en"):
    import re
    key = os.getenv("SARVAM_API_KEY")
    model = os.getenv("SARVAM_MODEL", "sarvam-105b")
    tl = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in TOOLS]
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"[app language: {lang}] {question}"}]
    used = []
    for _ in range(5):
        r = _sarvam_post({"model": model, "messages": msgs, "tools": tl, "tool_choice": "auto", "temperature": 0.2}, key)
        ch = r.get("choices") or []
        if not ch:
            raise RuntimeError("Sarvam returned no answer: " + str(r)[:200])
        m = ch[0]["message"]
        calls = m.get("tool_calls") or []
        if not calls:
            text = re.sub(r"<think>.*?</think>", "", m.get("content") or "", flags=re.S).strip()
            if not text:
                raise RuntimeError("Sarvam returned an empty answer")
            return tools.unmask(text), used
        msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            used.append(name)
            fn = tools.FUNCS.get(name)
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
                out = fn(**args) if fn else {"error": "unknown tool"}
            except Exception as e:
                out = {"error": str(e)}
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, ensure_ascii=False)})
    raise RuntimeError("AI used too many steps")


def _gemini_post(body, key, model):
    import urllib.request
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def _gemini_tools():
    decls = []
    for t in TOOLS:
        d = {"name": t["name"], "description": t["description"]}
        props = t["input_schema"].get("properties")
        if props:  # Gemini rejects empty parameter objects, so no-argument tools omit "parameters"
            d["parameters"] = {"type": "OBJECT", "properties": {
                k: {kk: (vv.upper() if kk == "type" else vv) for kk, vv in v.items()} for k, v in props.items()}}
        decls.append(d)
    return [{"functionDeclarations": decls}]


def ask_gemini(question, lang="en"):
    key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    contents = [{"role": "user", "parts": [{"text": f"[app language: {lang}] {question}"}]}]
    used = []
    for _ in range(5):
        r = _gemini_post({"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                          "tools": _gemini_tools(), "generationConfig": {"maxOutputTokens": 800}}, key, model)
        cands = r.get("candidates") or []
        if not cands or "content" not in cands[0]:
            raise RuntimeError("Gemini returned no answer: " + str(r)[:200])
        content = cands[0]["content"]
        parts = content.get("parts", [])
        calls = [x["functionCall"] for x in parts if "functionCall" in x]
        if not calls:
            text = "".join(x.get("text", "") for x in parts if not x.get("thought")).strip()
            return tools.unmask(text), used
        contents.append(content)  # keep the model's parts exactly as returned
        resp = []
        for c in calls:
            used.append(c["name"])
            fn = tools.FUNCS.get(c["name"])
            try:
                out = fn(**(c.get("args") or {})) if fn else {"error": "unknown tool"}
            except Exception as e:
                out = {"error": str(e)}
            resp.append({"functionResponse": {"name": c["name"], "response": {"result": out}}})
        contents.append({"role": "user", "parts": resp})
    raise RuntimeError("AI used too many steps")


def ask_claude(question, lang="en"):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    from anthropic import Anthropic  # imported here so the rest of the app runs without the package

    client = Anthropic()
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    msgs = [{"role": "user", "content": f"[app language: {lang}] {question}"}]
    used = []
    for _ in range(5):
        r = client.messages.create(model=model, max_tokens=600, system=SYSTEM, tools=TOOLS, messages=msgs)
        if r.stop_reason != "tool_use":
            text = "".join(b.text for b in r.content if b.type == "text").strip()
            return tools.unmask(text), used
        msgs.append({"role": "assistant", "content": r.content})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                used.append(b.name)
                fn = tools.FUNCS.get(b.name)
                try:
                    out = fn(**(b.input or {})) if fn else {"error": "unknown tool"}
                except Exception as e:
                    out = {"error": str(e)}
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": results})
    raise RuntimeError("AI used too many steps")
