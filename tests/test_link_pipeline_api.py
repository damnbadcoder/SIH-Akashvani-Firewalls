"""
Integration tests for Link Pipeline API endpoints.
Tests /api/pipeline/scrape-link, /api/pipeline/download-link-artifact,
and /api/generate-plan integration with sourceLinks.
"""

import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, init_db
from backend.models import User, SessionRecord, FileRecord
from pipelines.link_pipeline.scraper import LinkScraper


MOCK_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>CERT-In Advisory: Critical Infrastructure Vulnerability (CVE-2026-1122)</title>
    <meta name="description" content="Exploitation of CVE-2026-1122 targeting industrial control networks.">
    <meta name="author" content="National Cyber Response Team">
    <meta property="og:title" content="CERT-In Advisory: Critical Infrastructure Vulnerability (CVE-2026-1122)">
    <meta property="og:site_name" content="CERT-In">
</head>
<body>
    <article>
        <h1>CERT-In Advisory: Critical Infrastructure Vulnerability</h1>
        <p>Multiple attacks detected targeting SCADA telemetry gateways using <strong>CVE-2026-1122</strong>.</p>
        <p>Command infrastructure traced to <code>192.0.2.144</code> associated with <strong>Volt Typhoon</strong>.</p>
    </article>
</body>
</html>
"""


class TestLinkPipelineAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @patch.object(LinkScraper, "fetch_url")
    def test_01_scrape_link_endpoint(self, mock_fetch):
        mock_fetch.return_value = (
            MOCK_HTML,
            200,
            "text/html; charset=utf-8",
            {"server": "nginx", "content-type": "text/html"}
        )

        payload = {"url": "https://cert-in.org.in/advisories/cve-2026-1122"}
        res = self.client.post("/api/pipeline/scrape-link", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["domain"], "cert-in.org.in")
        self.assertIn("CVE-2026-1122", data["title"])
        self.assertIn("CVE-2026-1122", data["markdown"])
        self.assertIn("CVE-2026-1122", data["iocs"]["cves"])
        self.assertIn("192.0.2.144", data["iocs"]["ipv4_addresses"])
        self.assertIn("Volt Typhoon", data["iocs"]["threat_actors"])
        self.assertIsNotNone(data["md_file_path"])
        self.assertIsNotNone(data["json_file_path"])
        self.assertTrue(Path(data["md_file_path"]).exists())
        self.assertTrue(Path(data["json_file_path"]).exists())

        # Test download endpoint for generated .md
        md_download = self.client.get(f"/api/pipeline/download-link-artifact?path={data['md_file_path']}")
        self.assertEqual(md_download.status_code, 200)
        self.assertIn("CERT-In Advisory", md_download.text)

        # Test download endpoint for generated .json
        json_download = self.client.get(f"/api/pipeline/download-link-artifact?path={data['json_file_path']}")
        self.assertEqual(json_download.status_code, 200)
        json_data = json_download.json()
        self.assertEqual(json_data["metadata"]["domain"], "cert-in.org.in")

    @patch.object(LinkScraper, "fetch_url")
    def test_02_generate_plan_with_source_links(self, mock_fetch):
        mock_fetch.return_value = (
            MOCK_HTML,
            200,
            "text/html; charset=utf-8",
            {"server": "nginx"}
        )

        payload = {
            "sourceText": "",
            "sourceLinks": ["https://cert-in.org.in/advisories/cve-2026-1122"],
            "selected_outputs": ["exec_summary"],
            "parameters": {},
            "email": "analyst@cert-in.gov.in"
        }

        res = self.client.post("/api/generate-plan", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIn("previewsByType", data)
        # Verify citations include link citation
        link_citations = [c for c in data.get("citations", []) if c.get("kind") == "link"]
        self.assertGreaterEqual(len(link_citations), 1)

        # Verify FileRecord created in database
        session_id = data.get("sessionId") or data.get("session_id")
        self.assertIsNotNone(session_id)
        link_file = self.db.query(FileRecord).filter(
            FileRecord.session_id == session_id,
            FileRecord.file_type == "link"
        ).first()
        self.assertIsNotNone(link_file)
        self.assertIn("cert-in.org.in", link_file.filename)

    @patch.object(LinkScraper, "fetch_url")
    def test_03_generate_plan_multipart_link_only(self, mock_fetch):
        """
        Verify that frontend multipart/form-data requests with LINK-ONLY input
        (no uploaded files, no sourceText) succeed without UnboundLocalError.
        """
        mock_fetch.return_value = (
            MOCK_HTML,
            200,
            "text/html; charset=utf-8",
            {"server": "nginx"}
        )

        form_data = {
            "sourceText": "",
            "sourceLinks": json.dumps(["https://cert-in.org.in/advisories/cve-2026-1122"]),
            "outputs": json.dumps([{"id": "exec_summary", "params": {}}]),
            "isOrganisation": "false",
            "email": "researcher@cert-in.gov.in",
        }

        # Send as multipart/form-data without any 'files' field
        res = self.client.post("/api/generate-plan", data=form_data)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIn("previewsByType", data)
        self.assertIn("session_id", data)
        self.assertIn("citations", data)

        link_cits = [c for c in data.get("citations", []) if c.get("kind") == "link"]
        self.assertGreaterEqual(len(link_cits), 1)


if __name__ == "__main__":
    unittest.main()

