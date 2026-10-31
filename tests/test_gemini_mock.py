"""Checks the Gemini tool-calling loop without internet (the Google call is faked)."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["GEMINI_API_KEY"] = "fake"
import tempfile
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
from app import auth as _a, db as _d; _d.init(); _d.set_merchant(_a.register("9876543210", "password1", "Test Store", "Owner", sample=True)["merchant"]["id"])
from app import ai
calls = []
def fake(body, key, model):
    calls.append(body)
    if len(calls) == 1:
        assert "tools" in body and body["tools"][0]["functionDeclarations"]
        return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "khata_list", "args": {}}}]}}]}
    last = body["contents"][-1]["parts"][0]["functionResponse"]["response"]["result"]
    assert "Customer K1" in str(last) and "Sunita" not in str(last)
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": "Remind Customer K1 first."}]}}]}
ai._gemini_post = fake
ans, used = ai.ask("who owes me?", "en")
print(ans, used, ai.status())
assert ans == "Remind Sunita Devi first." and used == ["khata_list"]
decl = ai._gemini_tools()[0]["functionDeclarations"]
assert all("parameters" not in d for d in decl if d["name"] in ("sales_summary", "khata_list"))
print("GEMINI MOCK OK")
