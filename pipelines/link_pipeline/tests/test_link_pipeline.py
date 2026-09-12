"""
Unit & Integration Tests for Web Link Scraping Pipeline (link_pipeline).
Verifies HTML normalization, metadata extraction, deterministic IOC parsing,
and dual-payload (.md + .json) artifact emission.
"""

import os
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.link_pipeline.schema import (
    LinkMetadata,
    ExtractedLinkIOCs,
    LinkPipelineResult,
)
from pipelines.link_pipeline.scraper import LinkScraper
from pipelines.link_pipeline.formatter import format_link_to_markdown
from pipelines.link_pipeline.ingest import LinkPipeline, ingest_link


SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Critical Zero-Day CVE-2026-9999 Exploit Active in the Wild</title>
    <meta name="description" content="Threat actors exploiting unpatched remote code execution vulnerability across banking infrastructure.">
    <meta name="author" content="Elena Rostova">
    <meta property="og:title" content="Critical Zero-Day CVE-2026-9999 Exploit Active in the Wild">
    <meta property="og:description" content="Threat actors exploiting unpatched remote code execution vulnerability across banking infrastructure.">
    <meta property="og:site_name" content="CyberSec Weekly">
    <meta property="article:published_time" content="2026-09-12T14:30:00Z">
    <link rel="canonical" href="https://cybersecweekly.org/threats/cve-2026-9999">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Critical Zero-Day CVE-2026-9999 Exploit Active in the Wild",
        "datePublished": "2026-09-12T14:30:00Z",
        "author": {
            "@type": "Person",
            "name": "Elena Rostova"
        }
    }
    </script>
    <style>
        .banner { background: red; }
    </style>
</head>
<body>
    <header>
        <nav><a href="/">Home</a> | <a href="/news">News</a></nav>
    </header>

    <div class="ad-banner">50% off VPN today!</div>

    <article class="article-body">
        <h1>Critical Zero-Day CVE-2026-9999 Exploit Active in the Wild</h1>
        <p class="byline">By Elena Rostova | Published September 12, 2026</p>
        
        <p>Security researchers observed initial compromise campaigns targeting perimeter systems via <strong>CVE-2026-9999</strong>.</p>
        
        <h2>Threat Attribution & Indicators</h2>
        <p>Telemetry links the attacks to the <strong>Lazarus Group</strong> utilizing command and control infrastructure at <code>198.51.100.45</code> and secondary beacon <code>203.0.113.88</code>.</p>
        
        <p>Adversaries were observed executing MITRE ATT&CK technique <strong>T1059.001</strong> (PowerShell command execution) to deliver a malicious implant with SHA-256 hash: <code>e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855</code>.</p>

        <h3>Affected Components</h3>
        <table>
            <thead>
                <tr>
                    <th>Component</th>
                    <th>Vulnerable Version</th>
                    <th>Fixed Version</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>BankShield Auth Gateway</td>
                    <td>v2.1.0</td>
                    <td>v2.1.4</td>
                </tr>
                <tr>
                    <td>Edge Connect SSL Proxy</td>
                    <td>v4.0.2</td>
                    <td>v4.0.5</td>
                </tr>
            </tbody>
        </table>

        <blockquote>
            Administrators are strongly advised to apply emergency patches immediately and quarantine affected network segments.
        </blockquote>
    </article>

    <footer>
        <p>© 2026 CyberSec Weekly. All rights reserved.</p>
    </footer>
</body>
</html>
"""


class TestLinkPipeline(unittest.TestCase):

    def setUp(self):
        self.scraper = LinkScraper()

    def test_normalize_url(self):
        self.assertEqual(self.scraper.normalize_url("example.com"), "https://example.com")
        self.assertEqual(self.scraper.normalize_url("http://test.org/path"), "http://test.org/path")
        self.assertEqual(self.scraper.normalize_url("https://secure.site.com"), "https://secure.site.com")
        with self.assertRaises(ValueError):
            self.scraper.normalize_url("")

    @patch.object(LinkScraper, "fetch_url")
    def test_pipeline_scrape_and_file_generation(self, mock_fetch):
        # Mock HTML response
        mock_fetch.return_value = (
            SAMPLE_HTML,
            200,
            "text/html; charset=utf-8",
            {"server": "cloudflare", "content-type": "text/html; charset=utf-8"}
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = LinkPipeline(output_dir=tmpdir)
            result = pipeline.process("https://cybersecweekly.org/threats/cve-2026-9999")

            self.assertTrue(result.success)
            self.assertEqual(result.metadata.domain, "cybersecweekly.org")
            self.assertEqual(result.metadata.author, "Elena Rostova")
            self.assertIn("CVE-2026-9999", result.metadata.title)
            self.assertEqual(result.metadata.status_code, 200)

            # Check IOC extraction
            self.assertIn("CVE-2026-9999", result.iocs.cves)
            self.assertIn("198.51.100.45", result.iocs.ipv4_addresses)
            self.assertIn("203.0.113.88", result.iocs.ipv4_addresses)
            self.assertIn("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", result.iocs.sha256_hashes)
            self.assertIn("T1059.001", result.iocs.mitre_attack_ids)
            self.assertIn("Lazarus Group", result.iocs.threat_actors)

            # Check markdown table conversion
            self.assertIn("| BankShield Auth Gateway | v2.1.0 | v2.1.4 |", result.clean_markdown)

            # Check generated files
            self.assertIsNotNone(result.md_file_path)
            self.assertIsNotNone(result.json_file_path)
            self.assertTrue(Path(result.md_file_path).exists())
            self.assertTrue(Path(result.json_file_path).exists())

            # Verify saved markdown content
            md_content = Path(result.md_file_path).read_text(encoding="utf-8")
            self.assertIn("# Critical Zero-Day CVE-2026-9999", md_content)
            self.assertIn("Elena Rostova", md_content)

            # Verify saved json content
            json_content = json.loads(Path(result.json_file_path).read_text(encoding="utf-8"))
            self.assertEqual(json_content["metadata"]["domain"], "cybersecweekly.org")
            self.assertIn("CVE-2026-9999", json_content["iocs"]["cves"])

    @patch.object(LinkScraper, "fetch_url")
    def test_procedural_ingest_link(self, mock_fetch):
        mock_fetch.return_value = (
            SAMPLE_HTML,
            200,
            "text/html",
            {"server": "nginx"}
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            res = ingest_link("https://cert-in.org.in/advisory/2026-01", output_dir=tmpdir, save_outputs=True)
            self.assertTrue(res.success)
            self.assertEqual(res.metadata.domain, "cert-in.org.in")
            self.assertTrue(Path(res.md_file_path).exists())
            self.assertTrue(Path(res.json_file_path).exists())

    def test_error_resilience(self):
        pipeline = LinkPipeline()
        # Invalid host should not raise uncaught exception
        res = pipeline.process("https://nonexistent-domain-xyz-9876543210.invalid/test")
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error_message)


if __name__ == "__main__":
    unittest.main()
