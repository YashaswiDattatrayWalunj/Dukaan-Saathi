# Dukaan Saathi – working prototype (Paytm Build for India AI Hackathon, Track 1)

AI business partner for kirana merchants: voice briefing, smart restock, ask-anything (English / हिंदी / मराठी), khata reminders and growth nudges.
Runs on **sample CSV data** in `/data`. Soundbox, WhatsApp and lending are NOT connected.

## Run on Windows (easiest)
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Unzip this folder, open it in VS Code (File > Open Folder).
3. Double-click `run.bat`. It creates `.venv`, installs packages and opens http://127.0.0.1:8001

## Run from the VS Code terminal (PowerShell)
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```
If PowerShell blocks activation, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
Or press F5 in VS Code (Python extension installed) to use the included launch config.

## Folder map
- `static/index.html` – the dashboard (UI, voice, Ask Anything logic)
- `app/main.py` – FastAPI server (`/api/data`, `/api/upload/{kind}`, docs at `/docs`)
- `app/plan.py` – Today's Business Action Plan (ranking + approve/dismiss, no AI needed)
- `app/data.py` – reads the CSVs and builds the last 14 days per item
- `data/*.csv` – sales, stock, khata, customers (edit these in VS Code and refresh the page)
- `scripts/make_sample_data.py` – regenerate data for your demo date: `python scripts/make_sample_data.py 2026-10-31`

## Use your own data
Edit the CSVs, or open http://127.0.0.1:8001/docs, choose `POST /api/upload/{kind}` (sales, stock, khata or customers) and upload a file with the same column names. A bad file is rejected and the old data is kept.

## Demo order (3 minutes)
1. Problem: Soundbox says what came in, not what to do.
2. Play briefing (switch to हिंदी). 3. Smart Restock + Diwali toggle. 4. Ask by voice: "is hafte profit kitna hua?".
5. Khata reminder preview, growth nudge. 6. Ask: Soundbox + data access from Paytm.

## Be honest with judges
- Data is sample data; answers are calculated from it, never guessed.
- Ask Anything uses rules, not an LLM yet. An LLM can sit on top of the same calculations.
- Item-level sales need billing/inventory data; UPI alone shows only amounts.
- Marathi voice may be missing on some PCs (falls back to Hindi voice or text). Mic input needs Chrome/Edge and internet.

## Step 1: real AI in Ask Anything
1. Copy `.env.example` to `.env` and paste your Anthropic API key (console.anthropic.com > API keys).
2. Run `run.bat`, then open http://127.0.0.1:8001/api/ai-status. It should show `"configured": true`.
3. Ask a question in the page. Under each answer you will see "AI answer · numbers checked with: ...". If it says "Rule-based answer", the AI is offline and the page used its built-in rules.
4. How it works: the AI picks a tool from `app/tools.py`, Python calculates, the AI explains. Customer names are replaced by labels like "Customer K1" before the AI sees them and restored in the answer.
5. Check the numbers with `python tests/test_tools.py`.

### Free AI key (Gemini)
Get a free key at aistudio.google.com ("Get API key"), put it in `.env` as `GEMINI_API_KEY=...`, restart `run.bat`.
`/api/ai-status` then shows `"provider": "gemini"`. Free-tier requests may be used by Google to improve its products, so demo with sample data only.
If the model name is rejected, copy the current Flash model name from AI Studio into `GEMINI_MODEL`.

### Free AI key (Sarvam, Indian languages)
Sign in at indus.sarvam.ai, open API Keys, generate a key (starts with `sk_`), put it in `.env` as `SARVAM_API_KEY=...`, restart `run.bat`.
`/api/ai-status` then shows `"provider": "sarvam"`. To force one provider when several keys are set, add `AI_PROVIDER=sarvam` (or `gemini`, `claude`).

## Step 2: My shop (real data, saved)
- Open the page and scroll to **My shop**. Click **Start my own shop (empty)** to clear the demo data.
- **Add an item** (name, selling price, cost price, stock now, supplier days). Same name again updates it.
- **Quick sale:** tap an item each time you sell one. Stock goes down and the dashboard, briefing, restock and AI answers update at once. **Undo last sale** reverses the last tap.
- **Add udhaar** and mark it **Paid**. **Add a regular customer**; they appear under Growth Nudges when they are away for more than twice their usual gap. **Came today** resets that.
- Everything is saved in `data/dukaan.db` on this computer (it survives restarts). Delete that file to start again; it is not uploaded anywhere.
- Test the saving logic: `python tests/test_db.py` (uses a temporary database).
- **Reset to demo shop** brings back the sample data for the video and demo.
- If you use a free AI key (Gemini), Google may use those requests to improve its products. Use the demo shop for the AI while testing, and only enter real customer details once you are on a paid key or have the owner's permission.

## Step 3: Today's Business Action Plan
- A card near the top of the page shows the **3 most useful actions for today**, each with priority, reason, benefit and **Approve / Dismiss** (English, हिंदी, मराठी).
- How it is chosen (`app/plan.py`, plain Python, no AI): it scores stock risk (money you may lose if an item runs out before the supplier delivers), overdue udhaar (amount x how late) and regulars who stopped visiting (their average bill x how long they have been away). It takes the best of each kind so the plan covers stock, money and customers, then orders by priority.
- **Approve** prepares the content: the full order list, or a WhatsApp reminder / win-back offer. You can copy it, or press "Open WhatsApp" (wa.me link with the text filled in; you pick the customer and press send yourself). **Nothing is sent or ordered automatically**, and the dialog says so.
- **Dismiss** removes the action for today and the next best one takes its place. "Restore dismissed actions" brings them back. Choices are saved per day in `data/dukaan.db`.
- The "benefit" numbers are estimates from your own sales data, not guarantees.
- API: `GET /api/action-plan?lang=en|hi|mr`, `POST /api/action-plan/approve` `{key, lang}`, `POST /api/action-plan/dismiss` `{key}`, `POST /api/action-plan/restore`. Try them at /docs.
- Test: `pip install -r requirements.txt` then `python tests/test_plan.py`.

## Step 4: Login and one account per merchant
- First screen is now **Log in / Register** (English, हिंदी, मराठी). Register needs shop name, your name, a 10-digit mobile number and a password of 8+ characters. Tick "Start with sample data" to try the app, or leave it empty to enter your own shop. **Try a demo shop** makes a guest shop with sample data (guest shops are deleted after one day).
- The mobile number is only the **username**. No SMS or WhatsApp OTP is sent (that needs a paid provider). It is future scope.
- **Passwords** are saved only as scrypt hashes. After login the server gives a signed token (JWT, 7 days). Every data endpoint (`/api/data`, `/api/ask`, `/api/action-plan/...`, uploads, everything except `/api/health`, `/api/schema` and `/api/auth/...`) refuses requests without it.
- **One merchant cannot see another's data:** every table has a `merchant_id`, every query filters by it, and the database layer refuses to run a shop query when no merchant is signed in. The AI assistant only ever sees the signed-in merchant's numbers.
- 5 wrong passwords lock that mobile number for 5 minutes (counter is in memory and resets when the server restarts).
- **Customer mobile numbers (optional):** add them when you add udhaar or a regular customer (or as an optional `phone` column in the CSV). "Reminder" and the Action Plan then open WhatsApp on that customer's chat with the message filled in. You still press send yourself; nothing is sent automatically.
- The database file is now `data/dukaan.db`. The old `data/saathi.db` from Step 2/3 is not read (accounts did not exist then). Register again and re-enter or import your data.
- API: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/demo`, `GET /api/auth/me`, `POST /api/auth/profile`. Send `Authorization: Bearer <token>` on the others. In /docs use "Authorize" is not set up; use the page, or curl with the header.
- Tests: `python tests/test_auth.py` (login rules, lockout, forged/expired tokens, isolation between two merchants, 40 simultaneous requests from two merchants, WhatsApp number). Run `python tests/test_plan.py`, `test_db.py`, `test_tools.py` too.
- Not done yet (honest list): password reset / "forgot password", changing the shop name, HTTPS (comes with deployment), and moving from SQLite to PostgreSQL.


## Step 4: Paytm merchant report import (CSV; no live account connection claimed)

This build adds a **review-before-save** import for CSV reports that the merchant downloads from their authorized Paytm/merchant dashboard. It does not connect to a Paytm QR/Soundbox account automatically and does not invent a Paytm API endpoint.

1. Sign in to Dukaan Saathi.
2. Open `http://127.0.0.1:8001/docs`.
3. Use `POST /api/integrations/paytm/preview` with a CSV. It maps common headers and returns valid rows plus row-level errors without saving.
4. Review the preview. Then call `POST /api/integrations/paytm/confirm` with JSON body `{"rows":[...the reviewed rows...]}`.
5. Use `GET /api/integrations/paytm/summary` to see imported transaction count, successful collection total, status breakdown and recent transactions.

Required CSV fields: transaction ID, transaction date, amount and status. Optional fields: order ID, payment mode and transaction type. Original transaction IDs are unique per merchant; repeat imports are skipped, not overwritten. This importer supports CSV only, up to 2 MB and 10,000 rows per confirmation. Export column names vary by Paytm product/report, so use the preview errors to confirm mapping before saving.

**Important data boundaries:** imported payment amounts are collections, not item-level sales. Product-level sales still require billing/POS records or merchant-entered sales. Successful status matching currently recognizes `success`, `successful`, `captured`, `settled`, and `completed`; review the source report's status vocabulary before relying on totals. Settlement reconciliation, refund lifecycle tracking, live webhooks, Paytm production API calls, WhatsApp delivery, PostgreSQL, and React migration are not claimed as complete in this build.

### Step 4 test
With the virtual environment active:
```
python -m unittest tests.test_paytm_import -v
```
