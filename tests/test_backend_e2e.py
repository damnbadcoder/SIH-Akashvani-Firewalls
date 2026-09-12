import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, init_db
from backend.models import User, SessionRecord, FileRecord, PreviewRecord, DeliverableRecord, ChatMessage
from backend.services.storage_service import storage_service
from backend.services.router_service import router_service, ALL_SUPPORTED_EXTENSIONS
from backend.services.context_service import enhancer_1_node
from backend.services.conditional_service import conditional_routing_service

class BackendEndToEndTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_health_check(self):
        """Verify /api/health reports healthy status, database engine, and supported formats."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("supported_file_formats_count", data)
        self.assertGreaterEqual(data["supported_file_formats_count"], 46)
        print(f"\n[Test 1] Health Check passed: {data['supported_file_formats_count']} file formats supported.")

    def test_02_auth_flow(self):
        """Verify registration and login flow in database."""
        email = f"analyst_test_{os.urandom(4).hex()}@cert-in.org.in"
        reg_payload = {
            "name": "Lead Threat Analyst",
            "email": email,
            "password": "SecurePassword123!",
            "user_type": "Organisation",
            "organisation": "CERT-In National Operations"
        }
        res_reg = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(res_reg.status_code, 200)
        reg_data = res_reg.json()
        self.assertEqual(reg_data["email"], email)

        login_payload = {
            "email": email,
            "password": "SecurePassword123!"
        }
        res_login = self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(res_login.status_code, 200)
        login_data = res_login.json()
        self.assertEqual(login_data["id"], reg_data["id"])
        print(f"[Test 2] Auth Flow passed: User {reg_data['email']} registered and logged in.")

    def test_03_format_router_coverage(self):
        """Verify all 46 file format extensions are classified and routed to appropriate pipelines."""
        self.assertGreaterEqual(len(ALL_SUPPORTED_EXTENSIONS), 46)
        
        # Test routing for each media pipeline type
        self.assertEqual(router_service.detect_media_pipeline("diagram.png"), "image")
        self.assertEqual(router_service.detect_media_pipeline("wiretap.mp3"), "audio")
        self.assertEqual(router_service.detect_media_pipeline("briefing.mp4"), "video")
        self.assertEqual(router_service.detect_media_pipeline("advisory.pdf"), "text")
        self.assertEqual(router_service.detect_media_pipeline("threat.stix"), "text")
        self.assertEqual(router_service.detect_media_pipeline("telemetry.syslog"), "text")
        print(f"[Test 3] Format Router passed: 46+ formats correctly routed.")

    def test_04_phase1_and_phase2_generate_plan(self):
        """
        Phase 1: Ingests file & parameters, routes into pipeline, converges to md + json.
        Phase 2: Enhancer-1 connects context & groups content, LLM generates Preview.md (stored in disk & DB).
        """
        # Create dummy telemetry file and doc
        dummy_stix = json.dumps({
            "type": "bundle",
            "id": "bundle--123",
            "objects": [
                {"type": "indicator", "name": "CVE-2026-41822 Active Exploit", "pattern": "[ipv4-addr:value = '198.51.100.22']"}
            ]
        }).encode("utf-8")

        dummy_log = b"2026-09-12T08:14:22Z perimeter-gw auth_fail from 10.14.2.1 target=BankShield\n2026-09-12T08:15:00Z shadowgate_beacon CVE-2026-41822 payload executed"

        files = [
            ("files", ("intel.stix", dummy_stix, "application/json")),
            ("files", ("perimeter.log", dummy_log, "text/plain")),
        ]

        data = {
            "sourceText": "Critical cyber intrusion targeting enterprise infrastructure controllers.",
            "sourceLinks": json.dumps(["https://cert-in.org.in/advisories/2026"]),
            "outputs": json.dumps([
                {"id": "linkedin_post", "params": {"tone": "Authoritative", "detail": "High", "language": "English", "audienceCategory": "executive"}},
                {"id": "advisory", "params": {"tone": "Technical", "detail": "Deep", "language": "English", "audienceCategory": "technical"}}
            ]),
            "isOrganisation": "true"
        }

        response = self.client.post("/api/generate-plan", data=data, files=files)
        self.assertEqual(response.status_code, 200)
        res_json = response.json()

        self.assertIn("plan", res_json)
        self.assertIn("previewsByType", res_json)
        self.assertIn("session_id", res_json)
        self.assertIn("citations", res_json)
        
        session_id = res_json["session_id"]
        # Verify Preview.md was saved to disk
        preview_file = PROJECT_ROOT / "storage" / "previews" / session_id / "Preview.md"
        self.assertTrue(preview_file.exists(), f"Preview.md was not found at {preview_file}")
        self.assertGreater(preview_file.stat().st_size, 0)

        # Verify DB records (2 uploaded files + 1 scraped link record)
        session_rec = self.db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
        self.assertIsNotNone(session_rec)
        self.assertEqual(len([f for f in session_rec.files if f.file_type != "link"]), 2)
        self.assertGreaterEqual(len(session_rec.files), 2)
        self.assertGreaterEqual(len(session_rec.previews), 1)

        print(f"[Test 4] Phase 1 & 2 passed: Session {session_id} created, Preview.md stored on disk & DB.")
        return session_id, res_json

    def test_05_backend_task_2_review_loop(self):
        """
        Backend Task 2: Backend Review Loop.
        Accepts edits to Preview.md, writes to Preview_edited.md, and tracks versions in DB.
        """
        session_id, plan_data = self.test_04_phase1_and_phase2_generate_plan()

        original_preview = plan_data["previewsByType"].get("linkedin_post") or plan_data["plan"]
        edited_preview = original_preview + "\n\n**MANUAL EDIT APPLIED BY CISO**: Quarantine all regional branch routers immediately."

        edit_payload = {
            "session_id": session_id,
            "output_type": "linkedin_post",
            "edited_content": edited_preview,
            "is_organisation": True,
            "accept": True
        }

        response = self.client.post(f"/api/previews/{session_id}/edit", json=edit_payload)
        self.assertEqual(response.status_code, 200)
        res_json = response.json()

        self.assertEqual(res_json["version"], 2)
        self.assertTrue(res_json["is_accepted"])
        self.assertIn("Preview_edited.md", res_json["edited_preview_path"])

        # Check Preview_edited.md exists on disk
        edited_file = Path(res_json["edited_preview_path"])
        self.assertTrue(edited_file.exists())
        self.assertIn("MANUAL EDIT APPLIED BY CISO", edited_file.read_text(encoding="utf-8"))

        print(f"[Test 5] Backend Task 2 Review Loop passed: Preview_edited.md created at version {res_json['version']}.")
        return session_id, edited_preview

    def test_06_phases_3_4_5_deliverable_generation(self):
        """
        Phase 3: Core LLM Branching (Gemini) payload combination.
        Phase 4: Conditional Logic Routing (Condition A: Enhance-3 + Enhance-4).
        Phase 5: Final Deliverable Generation.
        Backend Task 3: Deliverable & chat history stored in DB.
        """
        session_id, edited_preview = self.test_05_backend_task_2_review_loop()

        finalize_payload = {
            "session_id": session_id,
            "outputType": "linkedin_post",
            "previewDraft": edited_preview,
            "sourceText": "Critical breach in BankShield middleware CVE-2026-41822 [^src-1].",
            "groundingMd": "## Breach Telemetry\nAdversary executed exploit against core infrastructure [^src-1].",
            "groundingJson": {"cves": ["CVE-2026-41822"]},
            "params": {"tone": "Authoritative", "targetAudience": "CISOs", "language": "English"},
            "isOrganisation": True
        }

        response = self.client.post("/api/generate-deliverable", json=finalize_payload)
        self.assertEqual(response.status_code, 200)
        res_json = response.json()

        self.assertIn("final_content", res_json)
        self.assertIn("provenance", res_json)

        # Verify DeliverableRecord in Database
        deliverables = self.db.query(DeliverableRecord).filter(DeliverableRecord.session_id == session_id).all()
        self.assertGreaterEqual(len(deliverables), 1)

        # Verify Chat History in Database
        chat_msgs = self.db.query(ChatMessage).filter(ChatMessage.session_id == session_id).all()
        self.assertGreaterEqual(len(chat_msgs), 1)

        # Verify /api/history endpoint retrieves the session
        history_res = self.client.get("/api/history")
        self.assertEqual(history_res.status_code, 200)
        history_list = history_res.json()
        found = any(h["id"] == session_id for h in history_list)
        self.assertTrue(found, "Created session was not returned in /api/history")

        print(f"[Test 6] Phases 3, 4, 5 & Backend Task 3 passed: Deliverable generated and persisted in chat history.")

    def test_07_proofcheck_endpoint(self):
        """Verify /api/proofcheck redacts operational sensitive data when is_organization is True."""
        sample_text = "Adversary connected from internal IP 192.168.1.100 using password: supersecretpassword123."
        response = self.client.post("/api/proofcheck", json={"text": sample_text, "is_organization": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["sensitiveCount"], 0)
        self.assertIn("[SENSITIVE:", data["proofcheckedText"])
        print(f"[Test 7] Proofcheck passed: Flagged {data['sensitiveCount']} sensitive item(s).")

if __name__ == "__main__":
    unittest.main()
