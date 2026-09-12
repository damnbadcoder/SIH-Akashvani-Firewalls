import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db

import uuid

class WorkflowLifecycleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_full_workflow_lifecycle(self):
        test_email = f"analyst_lifecycle_{uuid.uuid4().hex[:8]}@cert-in.org.in"

        # 1. Verify history is initially empty for this user
        r1 = self.client.get(f"/api/history?email={test_email}")
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json(), [], f"Expected empty history, got {r1.json()}")

        # 2. Generate Plan / Blueprint
        plan_payload = {
            "sourceText": "Critical threat detected in controller nodes. IP 192.168.1.50 affected.",
            "outputs": ["linkedin_post", "advisory"],
            "email": test_email,
        }
        r2 = self.client.post("/api/generate-plan", json=plan_payload)
        self.assertEqual(r2.status_code, 200, r2.text)
        plan_data = r2.json()
        session_id = plan_data.get("sessionId") or plan_data.get("session_id")
        self.assertTrue(bool(session_id), "session_id missing from plan response")
        self.assertEqual(plan_data.get("status"), "blueprint_ready")

        # 3. Verify Account Isolation in History
        r3 = self.client.get(f"/api/history?email={test_email}")
        self.assertEqual(r3.status_code, 200)
        hist = r3.json()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["status"], "blueprint_ready")

        r3_other = self.client.get("/api/history?email=isolated_other_user@gmail.com")
        self.assertEqual(r3_other.json(), [])

        # 4. Autosave draft
        r4 = self.client.post(f"/api/previews/{session_id}/autosave", json={
            "output_type": "linkedin_post",
            "edited_content": "Operator edited draft text with IOC containment."
        })
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4.json().get("status"), "autosaved")

        # 5. Deliverable Finalization
        r5 = self.client.post("/api/generate-deliverable", json={
            "platform_key": "linkedin_post",
            "approved_draft": "Operator edited draft text with IOC containment.",
            "content_md": "Critical threat detected in controller nodes.",
            "sessionId": session_id,
            "email": test_email,
        })
        self.assertEqual(r5.status_code, 200, r5.text)
        deliv_data = r5.json()
        self.assertEqual(deliv_data.get("status"), "completed")
        self.assertEqual(deliv_data.get("sessionId"), session_id)

        # 6. Deduplication check
        r6 = self.client.get(f"/api/history?email={test_email}")
        hist6 = r6.json()
        self.assertEqual(len(hist6), 1, f"Expected exactly 1 session in history (no duplicates), got {len(hist6)}")
        self.assertEqual(hist6[0]["status"], "completed")
        self.assertGreaterEqual(len(hist6[0]["deliverables"]), 1)

if __name__ == "__main__":
    unittest.main()
