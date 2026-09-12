import os
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db

class AuthSyncTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_auth_sync_new_and_update(self):
        # 1. Sync a new Google user
        sync_payload = {
            "name": "Firebase Tester",
            "email": "tester.firebase@gmail.com",
            "user_type": "Researcher",
            "organisation": "Cyber Threat Lab"
        }
        res = self.client.post("/api/auth/sync", json=sync_payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["name"], "Firebase Tester")
        self.assertEqual(data["email"], "tester.firebase@gmail.com")
        self.assertEqual(data["user_type"], "Researcher")
        self.assertEqual(data["organisation"], "Cyber Threat Lab")
        self.assertTrue(bool(data["id"]))

        # 2. Sync again with updated organisation
        sync_payload["organisation"] = "National Cyber Command"
        res2 = self.client.post("/api/auth/sync", json=sync_payload)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["organisation"], "National Cyber Command")
        self.assertEqual(data2["id"], data["id"])

if __name__ == "__main__":
    unittest.main()
