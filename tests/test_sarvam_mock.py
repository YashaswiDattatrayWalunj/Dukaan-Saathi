"""Checks the Sarvam tool-calling loop without internet (the Sarvam call is faked)."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"): os.environ.pop(k, None)
os.environ["SARVAM_API_KEY"] = "sk_fake"
import tempfile
os.environ["SAATHI_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SAATHI_TODAY"] = "2026-10-31"
from app import auth as _a, db as _d; _d.init(); _d.set_merchant(_a.register("9876543210", "password1", "Test Store", "Owner", sample=True)["merchant"]["id"])
from app import ai
n = []
def fake(body, key):
    n.append(1)
    if len(n) == 1:
        assert body["tools"][0]["type"] == "function" and body["messages"][0]["role"] == "system"
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "khata_list", "arguments": "{}"}}]}}]}
    t = body["messages"][-1]
    assert t["role"] == "tool" and t["tool_call_id"] == "c1" and "Sunita" not in t["content"]
    return {"choices": [{"message": {"role": "assistant", "content": "<think>x</think>Remind Customer K1 first."}}]}
ai._sarvam_post = fake
ans, used = ai.ask("who owes me?", "en")
print(ans, used, ai.status())
assert ans == "Remind Sunita Devi first." and used == ["khata_list"] and ai.status()["provider"] == "sarvam"
print("SARVAM MOCK OK")
