import os
import sys
import json
import base64
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure common packages are imported
for extra_pkg_path in [
    "/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/dist-packages",
    "/home/samyakjain/snap/antigravity-cli/common/local/lib/python3.12/site-packages",
]:
    if os.path.isdir(extra_pkg_path) and extra_pkg_path not in sys.path:
        sys.path.insert(0, extra_pkg_path)

from backend.services.signing import SigningService
from backend.database import SessionLocal, init_db
from backend.models.deliverable import DeliverableRecord
from backend.models.provenance_registry import ProvenanceRegistryRecord
from backend.models.session import SessionRecord
from backend.services.deliverable_service import deliverable_service
from fastapi.testclient import TestClient
from backend.main import app

class TestSigningAndTamperDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.signing_service = SigningService(keys_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_keypair_generation_and_encryption(self):
        """Verify Ed25519 keypair generation and encrypted storage."""
        key_id = self.signing_service.active_key_id
        self.assertTrue(key_id.startswith("transmute-key"))

        priv_file = Path(self.temp_dir.name) / f"{key_id}.enc"
        pub_file = Path(self.temp_dir.name) / f"{key_id}.pub"
        self.assertTrue(priv_file.exists())
        self.assertTrue(pub_file.exists())

        # Verify private key loads and decrypts
        priv_key = self.signing_service.load_private_key(key_id)
        self.assertIsNotNone(priv_key)

        # Verify public key loads
        pub_key = self.signing_service.load_public_key(key_id)
        self.assertIsNotNone(pub_key)

    def test_sign_and_verify_authentic(self):
        """Verify authentic deliverable signs and verifies successfully."""
        content = "# Advisory: LockBit Ransomware Campaign\nIOC: 198.51.100.23\nStatus: Mitigated"
        envelope = self.signing_service.sign_deliverable(
            content=content,
            deliverable_id="deliv-test-01",
            output_type="advisory",
            organization="Acme Threat Intel",
            tlp_level="TLP:AMBER",
        )

        self.assertIn("signature", envelope)
        self.assertIn("content_sha256", envelope)
        self.assertIn("qr_data_url", envelope)
        self.assertTrue(envelope["qr_data_url"].startswith("data:image/png;base64,"))

        # Verify authentic
        res = self.signing_service.verify_deliverable(
            content=content,
            signature=envelope["signature"],
            signing_key_id=envelope["signing_key_id"],
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "AUTHENTIC")

    def test_tamper_detection_breaks_signature(self):
        """Verify modifying even a single byte or character triggers TAMPERED status."""
        original_content = "Advisory: Critical Zero-Day CVE-2026-9999 discovered in Ingress Controller."
        envelope = self.signing_service.sign_deliverable(
            content=original_content,
            deliverable_id="deliv-test-02",
            output_type="advisory",
        )

        # 1. Subtle character modification (tampering)
        tampered_content = "Advisory: Critical Zero-Day CVE-2026-9998 discovered in Ingress Controller."
        res = self.signing_service.verify_deliverable(
            content=tampered_content,
            signature=envelope["signature"],
            signing_key_id=envelope["signing_key_id"],
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "TAMPERED")

        # 2. Hash mismatch detection when expected_hash is asserted
        res_mismatch = self.signing_service.verify_deliverable(
            content=tampered_content,
            signature=envelope["signature"],
            signing_key_id=envelope["signing_key_id"],
            expected_hash=envelope["content_sha256"],
        )
        self.assertFalse(res_mismatch["valid"])
        self.assertEqual(res_mismatch["status"], "HASH_MISMATCH")

    def test_key_rotation_preserves_historical_verification(self):
        """Verify deliverables signed with rotated keys remain verifiable."""
        old_content = "Historical Advisory signed with Key V1"
        old_envelope = self.signing_service.sign_deliverable(
            content=old_content,
            deliverable_id="deliv-old-01",
            output_type="advisory",
        )
        old_key_id = old_envelope["signing_key_id"]

        # Rotate key
        new_key_id = self.signing_service.generate_keypair("transmute-key-2026-v2")
        self.assertEqual(self.signing_service.active_key_id, new_key_id)
        self.assertNotEqual(old_key_id, new_key_id)

        # Old deliverable must still verify with old_key_id
        res = self.signing_service.verify_deliverable(
            content=old_content,
            signature=old_envelope["signature"],
            signing_key_id=old_key_id,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "AUTHENTIC")

    def test_deliverable_service_persists_signature_and_provenance(self):
        """Verify DeliverableService registers the signature in database and ProvenanceRegistryRecord."""
        db = SessionLocal()
        try:
            # Create session
            session = SessionRecord(title="Test Provenance Session", status="blueprint_ready")
            db.add(session)
            db.commit()
            db.refresh(session)

            res = deliverable_service.generate_and_persist_deliverable(
                db=db,
                session_id=session.id,
                platform_key="advisory",
                routed_draft="### Threat Alert\nSystem compromised by CVE-2026-1111.",
                content_md="Evidence content about CVE-2026-1111.",
                metadata_json={"organization": "National Cyber CERT", "tlp_level": "TLP:RED"},
                parameters={"organization": "National Cyber CERT", "tlp_level": "TLP:RED"},
            )

            self.assertIn("signature", res)
            self.assertIn("content_hash", res)
            self.assertIn("qr_data_url", res)
            deliv_id = res["deliverable_id"]

            # Query database records
            deliv_record = db.query(DeliverableRecord).filter(DeliverableRecord.id == deliv_id).first()
            self.assertIsNotNone(deliv_record)
            self.assertEqual(deliv_record.signature, res["signature"])
            self.assertEqual(deliv_record.content_hash, res["content_hash"])

            # Query ProvenanceRegistryRecord
            reg_record = db.query(ProvenanceRegistryRecord).filter(
                ProvenanceRegistryRecord.deliverable_id == deliv_id
            ).first()
            self.assertIsNotNone(reg_record)
            self.assertEqual(reg_record.content_hash, res["content_hash"])
            self.assertEqual(reg_record.organization, "National Cyber CERT")
            self.assertEqual(reg_record.tlp_level, "TLP:RED")

            # Test create_revision (re-signing on edits)
            edited_content = res["content"] + "\n\n*Addendum: Patch released.*"
            rev_res = deliverable_service.create_revision(
                db=db,
                deliverable_id=deliv_id,
                updated_content=edited_content,
            )
            self.assertEqual(rev_res["revision"], 2)
            self.assertNotEqual(rev_res["content_hash"], res["content_hash"])
            self.assertNotEqual(rev_res["signature"], res["signature"])

            # Both revisions should exist in ProvenanceRegistry
            entries = db.query(ProvenanceRegistryRecord).filter(
                ProvenanceRegistryRecord.deliverable_id == deliv_id
            ).order_by(ProvenanceRegistryRecord.revision.asc()).all()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].revision, 1)
            self.assertEqual(entries[1].revision, 2)

        finally:
            db.close()

    def test_api_verify_endpoints(self):
        """Verify HTTP endpoints for signature verification, registry queries, and public keys."""
        # 1. Test public keys endpoint
        pub_keys_res = self.client.get("/api/v1/deliverables/public-keys")
        self.assertEqual(pub_keys_res.status_code, 200)
        keys_data = pub_keys_res.json()
        self.assertIn("keys", keys_data)
        self.assertGreater(len(keys_data["keys"]), 0)

        active_key = keys_data["keys"][0]["key_id"]

        # 2. Test raw PEM export endpoint
        pem_res = self.client.get(f"/api/v1/deliverables/public-keys/{active_key}")
        self.assertEqual(pem_res.status_code, 200)
        self.assertIn("BEGIN PUBLIC KEY", pem_res.text)

        # 3. Create a deliverable and verify via POST /api/v1/deliverables/verify
        db = SessionLocal()
        try:
            session = SessionRecord(title="API Test Session", status="blueprint_ready")
            db.add(session)
            db.commit()
            db.refresh(session)

            gen_res = deliverable_service.generate_and_persist_deliverable(
                db=db,
                session_id=session.id,
                platform_key="incident_report",
                routed_draft="# Incident Report 101\nHost quarantine active.",
                content_md="Telemetry evidence.",
                metadata_json={},
                parameters={},
            )
            deliv_id = gen_res["deliverable_id"]
            content = gen_res["content"]
            sig = gen_res["signature"]
            key_id = gen_res["signing_key_id"]
            c_hash = gen_res["content_hash"]
        finally:
            db.close()

        # Direct JSON verification (Authentic)
        verify_json_res = self.client.post("/api/v1/deliverables/verify", json={
            "content": content,
            "signature": sig,
            "signing_key_id": key_id,
        })
        self.assertEqual(verify_json_res.status_code, 200)
        v_data = verify_json_res.json()
        self.assertTrue(v_data["valid"])
        self.assertEqual(v_data["status"], "AUTHENTIC")
        self.assertTrue(v_data["in_registry"])

        # Tampered content verification
        verify_tampered = self.client.post("/api/v1/deliverables/verify", json={
            "content": content + " [HACKED]",
            "signature": sig,
            "signing_key_id": key_id,
        })
        self.assertEqual(verify_tampered.status_code, 200)
        self.assertFalse(verify_tampered.json()["valid"])
        self.assertEqual(verify_tampered.json()["status"], "TAMPERED")

        # Registry lookup by hash
        reg_res = self.client.get(f"/api/v1/deliverables/registry/{c_hash}")
        self.assertEqual(reg_res.status_code, 200)
        self.assertEqual(reg_res.json()["deliverable_id"], deliv_id)

        # Multipart form with sidecar file
        sidecar_dict = {
            "deliverable_id": deliv_id,
            "signature": sig,
            "signing_key_id": key_id,
            "content_sha256": c_hash,
            "organization": "Transmute Threat Intel CERT",
        }
        multipart_res = self.client.post(
            "/api/v1/deliverables/verify",
            files={
                "file": ("advisory.md", content.encode("utf-8"), "text/markdown"),
                "sig_file": ("advisory.sig", json.dumps(sidecar_dict).encode("utf-8"), "application/json"),
            }
        )
        self.assertEqual(multipart_res.status_code, 200)
        self.assertTrue(multipart_res.json()["valid"])
        self.assertEqual(multipart_res.json()["status"], "AUTHENTIC")

if __name__ == "__main__":
    unittest.main()
