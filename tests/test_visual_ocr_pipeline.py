"""
Comprehensive Test Suite for Visual OCR Coordinate Grounding and Interactive Bounding Box Inspector.
Validates:
1. OCR coordinate detection with normalized percentages (0.0 - 100.0%)
2. Verbatim / phrase fuzzy matching to 2D bounding boxes
3. ImagePipeline grounding attribution with BoundingBox models
4. FastAPI media endpoint GET /api/pipeline/media/{session_id}/{filepath}
5. PDF visual page rendering and OCR coordinates extraction
"""
import pytest
import os
from pathlib import Path
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.services.router_service import router_service
from pipelines.image_pipeline.extractors.ocr_utils import ImageOCRUtils
from pipelines.image_pipeline import ImagePipeline, ingest_image, BoundingBox, GroundingAnchor


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def synthetic_diagram_image(tmp_path):
    """Creates a temporary synthetic diagram image with distinct labelled nodes."""
    img_path = tmp_path / "threat_topology.png"
    img = Image.new("RGB", (800, 500), color="#0a0e17")
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((30, 20), "ADVANCED PERSISTENT THREAT (APT29) EXPLOIT TOPOLOGY", fill="#38bdf8")

    # Node 1: Ingress
    draw.rectangle([(40, 80), (320, 180)], outline="#f59e0b", width=2)
    draw.text((50, 95), "Initial Access: CVE-2024-21887", fill="#f59e0b")
    draw.text((50, 125), "Ivanti Connect Secure Zero-Day Injection", fill="#e2e8f0")

    # Node 2: C2 Server
    draw.rectangle([(440, 80), (740, 180)], outline="#ef4444", width=2)
    draw.text((450, 95), "Command and Control Beacon", fill="#ef4444")
    draw.text((450, 125), "Host IP: 198.51.100.44 Port: 8443", fill="#e2e8f0")

    # Node 3: Exfiltration
    draw.rectangle([(240, 280), (560, 380)], outline="#10b981", width=2)
    draw.text((250, 295), "Data Exfiltration Target", fill="#10b981")
    draw.text((250, 325), "Sensitive Telemetry Database Staging", fill="#e2e8f0")

    img.save(str(img_path))
    return str(img_path)


class TestVisualOCRUtils:
    def test_ocr_box_detection_and_normalization(self, synthetic_diagram_image):
        """Validates that OCR detects boxes with normalized coordinates between 0 and 100%."""
        res = ImageOCRUtils.detect_ocr_boxes(synthetic_diagram_image)
        assert "boxes" in res
        assert "resolution" in res
        assert res["resolution"] == (800, 500)
        assert len(res["boxes"]) > 0

        for box in res["boxes"]:
            b = box["bbox"]
            assert 0.0 <= b["x"] <= 100.0
            assert 0.0 <= b["y"] <= 100.0
            assert 0.1 <= b["width"] <= 100.0
            assert 0.1 <= b["height"] <= 100.0
            assert b["x"] + b["width"] <= 101.0  # slight tolerance for rounding
            assert b["y"] + b["height"] <= 101.0

    def test_phrase_to_bbox_matching(self, synthetic_diagram_image):
        """Verifies that verbatim text extracts match corresponding coordinates."""
        res = ImageOCRUtils.detect_ocr_boxes(synthetic_diagram_image)
        boxes = res["boxes"]

        # Match CVE finding
        matched_cve = ImageOCRUtils.match_phrase_to_bbox("CVE-2024-21887", boxes)
        assert matched_cve is not None
        assert 0.0 <= matched_cve["x"] <= 50.0  # located on left side
        assert 10.0 <= matched_cve["y"] <= 45.0

        # Match C2 beacon
        matched_c2 = ImageOCRUtils.match_phrase_to_bbox("Command and Control Beacon", boxes)
        assert matched_c2 is not None
        assert matched_c2["x"] >= 50.0  # located on right side
        assert 10.0 <= matched_c2["y"] <= 45.0

    def test_mock_diagram_generation(self, tmp_path):
        """Ensures high-fidelity mock diagram generation produces valid PNG image bytes."""
        out_file = tmp_path / "mock_nist.png"
        raw_bytes = ImageOCRUtils.generate_mock_diagram_image(str(out_file))
        assert len(raw_bytes) > 1000
        assert out_file.exists()
        assert out_file.stat().st_size > 1000

        # Test PIL can open it
        img = Image.open(str(out_file))
        assert img.size == (1200, 750)


class TestImagePipelineBoundingBoxes:
    def test_image_pipeline_produces_anchors_with_bboxes(self, synthetic_diagram_image):
        """Validates that ImagePipeline outputs grounding sources with 2D BoundingBox objects."""
        pipeline = ImagePipeline()
        res = pipeline.process(synthetic_diagram_image, force_mock=True)

        assert len(res.grounding_sources) > 0
        for anchor in res.grounding_sources:
            assert isinstance(anchor, GroundingAnchor)
            assert anchor.bbox is not None
            assert isinstance(anchor.bbox, BoundingBox)
            assert 0.0 <= anchor.bbox.x <= 100.0
            assert 0.0 <= anchor.bbox.y <= 100.0
            assert 0.0 < anchor.bbox.width <= 100.0
            assert 0.0 < anchor.bbox.height <= 100.0


class TestMediaServingEndpoint:
    def test_media_serving_endpoint(self, client):
        """Verifies GET /api/pipeline/media serves diagram PNG files."""
        res = client.get("/api/pipeline/media/default/1.png")
        assert res.status_code == 200
        assert "image/" in res.headers.get("content-type", "")
        assert len(res.content) > 1000

    def test_media_serving_fallback_diagram(self, client):
        """Verifies GET /api/pipeline/media serves fallback mock diagram when requested."""
        res = client.get("/api/pipeline/media/default/nist_csf_mock.png")
        assert res.status_code == 200
        assert "image/png" in res.headers.get("content-type", "")
        assert len(res.content) > 1000

    def test_media_serving_path_traversal_blocked(self, client):
        """Ensures directory traversal attacks are safely blocked."""
        res = client.get("/api/pipeline/media/default/../../etc/passwd")
        assert res.status_code in (404, 403)


class TestPDFVisualParsing:
    def test_pdf_visual_page_rendering_in_router(self, tmp_path):
        """Tests that PDFs with visual diagrams trigger page rendering and OCR coordinates."""
        pdf_path = "MediaPublish_AutomotiveCyberSecurity.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Test PDF not found at {pdf_path}")

        session_id = "test_pdf_session"
        processed = router_service.process_file_into_context(
            file_path=pdf_path,
            filename="MediaPublish_AutomotiveCyberSecurity.pdf",
            session_id=session_id,
        )

        assert "markdown" in processed
        assert "citations" in processed

        # Check if visual citation was created for the visual page
        ocr_citations = [c for c in processed["citations"] if c.get("kind") == "ocr" or c.get("bbox")]
        assert len(ocr_citations) > 0

        first_ocr = ocr_citations[0]
        assert "bbox" in first_ocr
        assert "media_url" in first_ocr
        assert 0.0 <= first_ocr["bbox"]["x"] <= 100.0
        assert 0.0 <= first_ocr["bbox"]["y"] <= 100.0
