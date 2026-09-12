import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.router_service import router_service

class RealMultimodalIngestTest(unittest.TestCase):
    def test_ingest_sample_pdf(self):
        pdf_path = PROJECT_ROOT / "tests" / "MediaPublish_AutomotiveCyberSecurity.pdf"
        if not pdf_path.exists():
            self.skipTest("Sample PDF not found")
        res = router_service.process_file_into_context(str(pdf_path), pdf_path.name)
        self.assertEqual(res["pipeline"], "text")
        self.assertGreater(len(res["markdown"]), 100)
        self.assertGreaterEqual(len(res["citations"]), 1)
        print(f"\n[Real PDF Ingest] Extracted {len(res['markdown'])} chars from {pdf_path.name}")

    def test_ingest_sample_image(self):
        img_path = PROJECT_ROOT / "tests" / "1.png"
        if not img_path.exists():
            self.skipTest("Sample PNG not found")
        res = router_service.process_file_into_context(str(img_path), img_path.name)
        self.assertEqual(res["pipeline"], "image")
        self.assertGreater(len(res["markdown"]), 100)
        print(f"[Real Image Ingest] Extracted {len(res['markdown'])} chars from {img_path.name}")

    def test_ingest_sample_audio(self):
        audio_path = PROJECT_ROOT / "tests" / "10090.mp3"
        if not audio_path.exists():
            self.skipTest("Sample MP3 not found")
        res = router_service.process_file_into_context(str(audio_path), audio_path.name)
        self.assertEqual(res["pipeline"], "audio")
        self.assertGreater(len(res["markdown"]), 100)
        print(f"[Real Audio Ingest] Extracted {len(res['markdown'])} chars from {audio_path.name}")

    def test_ingest_sample_video(self):
        video_path = PROJECT_ROOT / "tests" / "FBI CYD STRATEGY 2026 VIDEO 1080P HD.mp4"
        if not video_path.exists():
            self.skipTest("Sample MP4 not found")
        res = router_service.process_file_into_context(str(video_path), video_path.name)
        self.assertEqual(res["pipeline"], "video")
        self.assertGreater(len(res["markdown"]), 100)
        print(f"[Real Video Ingest] Extracted {len(res['markdown'])} chars from {video_path.name}")

if __name__ == "__main__":
    unittest.main()
