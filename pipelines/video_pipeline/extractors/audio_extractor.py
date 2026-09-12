"""
Audio extraction and speech-to-text transcription module for video pipelines.
Uses ffmpeg to demux audio and Groq Whisper (whisper-large-v3) for timestamped segments.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

from pipelines.video_pipeline.schema import AudioSegment

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

try:
    import whisper
    OPENAI_WHISPER_AVAILABLE = True
except ImportError:
    OPENAI_WHISPER_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


class VideoAudioExtractor:
    """Extracts audio track from video files and produces timestamped transcription segments."""

    def __init__(self, groq_api_key: Optional[str] = None):
        self.api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.api_key) if (GROQ_AVAILABLE and self.api_key) else None
        self._whisper_model = None

    def extract_audio(self, video_path: str, output_audio_path: Optional[str] = None) -> Optional[str]:
        """
        Uses ffmpeg to extract a 16kHz mono audio track from a video.

        Args:
            video_path: Path to video file (.mp4, .mkv, .avi, etc.).
            output_audio_path: Optional destination path for .wav file.

        Returns:
            Path to extracted audio file, or None if extraction fails or no audio track exists.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if output_audio_path is None:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(temp_fd)
            output_audio_path = temp_path

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path)
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 1000:
                return output_audio_path
            return None
        except (subprocess.CalledProcessError, FileNotFoundError):
            # No audio track or ffmpeg execution failed
            if os.path.exists(output_audio_path):
                try:
                    os.unlink(output_audio_path)
                except OSError:
                    pass
            return None

    def transcribe(self, audio_path: str) -> Tuple[str, List[AudioSegment]]:
        """
        Transcribes audio using Whisper / faster-whisper or Groq Whisper API (whisper-large-v3) with timestamped segments.
        Applies loop prevention parameters:
        condition_on_previous_text=False, temperature fallback, compression_ratio_threshold=2.4, no_speech_threshold=0.6.

        Args:
            audio_path: Path to WAV/MP3 audio file.

        Returns:
            Tuple of (full_transcript_text, list_of_AudioSegments).
        """
        if not audio_path or not os.path.exists(audio_path):
            return "", []

        # 1. Preferred: faster-whisper (offline, fast, loop-safe)
        if FASTER_WHISPER_AVAILABLE:
            try:
                if self._whisper_model is None:
                    self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
                raw_segments, info = self._whisper_model.transcribe(
                    audio_path,
                    condition_on_previous_text=False,
                    temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
                    compression_ratio_threshold=2.4,
                    no_speech_threshold=0.6,
                )
                segments: List[AudioSegment] = []
                text_parts: List[str] = []
                for idx, seg in enumerate(raw_segments, start=1):
                    txt = seg.text.strip()
                    if txt:
                        text_parts.append(txt)
                        segments.append(AudioSegment(
                            segment_id=idx,
                            start_seconds=round(float(seg.start), 2),
                            end_seconds=round(float(seg.end), 2),
                            text=txt
                        ))
                full_text = " ".join(text_parts)
                if segments:
                    return full_text, segments
            except Exception as e:
                print(f"[!] Warning: faster-whisper transcription error ({e}), trying fallback...", flush=True)

        # 2. Alternative local: openai-whisper
        if OPENAI_WHISPER_AVAILABLE:
            try:
                if self._whisper_model is None:
                    self._whisper_model = whisper.load_model("base")
                result = self._whisper_model.transcribe(
                    audio_path,
                    condition_on_previous_text=False,
                    temperature=(0.0, 0.2, 0.4, 0.6, 0.8),
                    compression_ratio_threshold=2.4,
                    no_speech_threshold=0.6,
                )
                segments: List[AudioSegment] = []
                raw_segments = result.get("segments", [])
                for idx, seg in enumerate(raw_segments, start=1):
                    txt = seg.get("text", "").strip()
                    if txt:
                        segments.append(AudioSegment(
                            segment_id=idx,
                            start_seconds=round(float(seg.get("start", 0.0)), 2),
                            end_seconds=round(float(seg.get("end", 0.0)), 2),
                            text=txt
                        ))
                full_text = result.get("text", "").strip()
                if segments:
                    return full_text, segments
            except Exception as e:
                print(f"[!] Warning: whisper transcription error ({e}), trying fallback...", flush=True)

        # 3. Cloud fallback: Groq Whisper API
        if self.groq_client:
            try:
                with open(audio_path, "rb") as f:
                    transcription = self.groq_client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), f.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                        temperature=0.2,
                    )

                full_text = transcription.text if hasattr(transcription, "text") else ""
                segments: List[AudioSegment] = []

                raw_segments = getattr(transcription, "segments", [])
                for idx, seg in enumerate(raw_segments, start=1):
                    start = float(seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0))
                    end = float(seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0))
                    txt = (seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip()

                    if txt:
                        segments.append(AudioSegment(
                            segment_id=idx,
                            start_seconds=round(start, 2),
                            end_seconds=round(end, 2),
                            text=txt
                        ))

                return full_text, segments
            except Exception as err:
                print(f"[!] Warning: Groq Whisper transcription encountered error: {err}", flush=True)
                return "", []

        print("[!] Note: No speech-to-text engine available (faster-whisper, whisper, or Groq API key).", flush=True)
        return "", []
