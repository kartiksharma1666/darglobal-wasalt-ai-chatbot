import os, tempfile, unittest
from app import store

class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        os.environ["DATABASE_PATH"] = self.tmp.name
        # Reload config constant used by store
        store.DATABASE_PATH = self.tmp.name
        store.init_db()
        store.upsert_document("https://wasalt.sa/en", "Wasalt", "Wasalt FAQ",
            "Wasalt is a Saudi real estate platform for buying renting and listing properties.", "2026-11-18T00:00:00Z")
    def tearDown(self):
        os.unlink(self.tmp.name)
    def test_search_returns_relevant_document(self):
        results = store.search_documents("How do I list property on Wasalt?")
        self.assertTrue(results)
        self.assertEqual(results[0]["domain"], "Wasalt")

if __name__ == "__main__":
    unittest.main()
