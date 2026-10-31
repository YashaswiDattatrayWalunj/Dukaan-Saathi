import os, tempfile, unittest
from pathlib import Path
from app import db, paytm_import

class PaytmCSVTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ["SAATHI_DB"]=str(Path(self.tmp.name)/"test.db")
        db._ready.clear(); db.init()
        with db.conn() as c:
            c.execute("INSERT INTO merchants(phone,shop_name,owner_name,pw_hash,created) VALUES(?,?,?,?,?)",
                      ("919876543210","Test Shop","Tester","x","2026-10-31"))
            mid=c.execute("SELECT id FROM merchants").fetchone()["id"]
        db.set_merchant(mid)
    def tearDown(self):
        self.tmp.cleanup(); os.environ.pop("SAATHI_DB",None); db._ready.clear()
    def test_parse_and_duplicate_safe_commit(self):
        raw=b"Transaction ID,Transaction Date,Amount,Status,Order ID\nTXN-1,2026-10-30,125.50,SUCCESS,ORD-1\nTXN-2,31/10/2026,20,FAILED,ORD-2\n"
        parsed=paytm_import.parse(raw)
        self.assertEqual(parsed["valid_count"],2)
        self.assertEqual(paytm_import.commit(parsed["rows"])["inserted"],2)
        self.assertEqual(paytm_import.commit(parsed["rows"])["duplicates_skipped"],2)
        self.assertEqual(paytm_import.summary()["successful_collections_rs"],125.5)
    def test_bad_csv_rejected(self):
        with self.assertRaises(ValueError): paytm_import.parse(b"foo,bar\nx,y\n")
if __name__=="__main__": unittest.main()
