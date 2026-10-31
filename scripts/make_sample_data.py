"""Makes demo CSV files in /data. Run: python scripts/make_sample_data.py [YYYY-MM-DD]
Pass the demo date so "today" in the dashboard matches the day you present."""
import csv, math, sys, datetime as dt
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data"
today = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
# id, English, Hindi, Marathi, price, cost, stock, lead days, festival uplift, base/day, trend
P = [("parle", "Parle-G", "पार्ले-जी", "पार्ले-जी", 10, 8, 38, 2, 1.3, 30, .04),
     ("milk", "Amul milk", "अमूल दूध", "अमूल दूध", 32, 29, 70, 1, 1.15, 24, .01),
     ("maggi", "Maggi", "मैगी", "मॅगी", 14, 11, 90, 3, 1.1, 12, 0),
     ("tea", "Tata Tea 250g", "टाटा चाय 250g", "टाटा चहा 250g", 135, 112, 30, 3, 1.15, 3, .02),
     ("atta", "Atta 5kg", "आटा 5kg", "आटा 5kg", 285, 250, 6, 2, 1.25, 2.5, .03),
     ("sweets", "Sweets box", "मिठाई बॉक्स", "मिठाई बॉक्स", 120, 90, 24, 2, 2.0, 4, .1)]


def rnd(i, d):
    x = math.sin(i * 12.9898 + d * 78.233) * 43758.5453
    return x - math.floor(x)


with open(D / "sales.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["date", "product_id", "qty"])
    for i, p in enumerate(P):
        for d in range(13, -1, -1):
            day = today - dt.timedelta(days=d)
            wk = 1.25 if day.weekday() >= 5 else 1
            q = max(0, int(p[9] * (1 + p[10] * (13 - d) / 2) * wk * (.85 + .3 * rnd(i, d)) + .5))
            w.writerow([day.isoformat(), p[0], q])
with open(D / "stock.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["product_id", "name_en", "name_hi", "name_mr", "price", "cost", "stock", "lead_days", "festival_uplift"])
    for p in P: w.writerow(p[:9])
with open(D / "khata.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["name", "amount", "days_overdue"])
    w.writerows([["Sunita Devi", 780, 15], ["Meena Tai", 1250, 9], ["Rahul Sharma", 500, 3], ["Imran Bhai", 320, -2]])
with open(D / "customers.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["name", "visit_every_days", "days_away", "avg_bill"])
    w.writerows([["Priya Nair", 7, 24, 420], ["Vikas Patil", 5, 19, 260], ["Anita Joshi", 10, 31, 680]])
print("Sample data written for", today)
