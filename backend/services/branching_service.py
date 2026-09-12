import os
import json
import re
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

class BranchingService:
    """
    Phase 3: Core LLM Branching (Gemini).
    Processes the edited preview alongside original md + json and newly generated enhanced key points.
    """

    @staticmethod
    def prepare_branch_payload(
        edited_preview: str,
        original_md: str,
        original_json: Dict[str, Any],
        enhanced_key_points: List[str],
        platform_key: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Payload Combination:
        Combines edited preview + original md + original json + enhanced key points into a unified branch payload.
        """
        combined_payload = {
            "platform_key": platform_key,
            "edited_preview": edited_preview,
            "original_md": original_md,
            "original_json": original_json,
            "enhanced_key_points": enhanced_key_points,
            "parameters": parameters,
        }
        return combined_payload

    @staticmethod
    def execute_gemini_branch(
        branch_payload: Dict[str, Any]
    ) -> str:
        """
        Routes the combined payload through the designated Gemini branch model.
        """
        edited_preview = branch_payload["edited_preview"]
        original_md = branch_payload["original_md"]
        original_json = branch_payload["original_json"]
        enhanced_key_points = branch_payload["enhanced_key_points"]
        platform_key = branch_payload["platform_key"]
        parameters = branch_payload["parameters"]

        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()

        prompt = (
            f"You are the Core LLM Branching Node for {platform_key}.\n"
            f"Integrate this edited preview with the foundational context and enhanced key points.\n\n"
            f"<ENHANCED_KEY_POINTS>\n" + "\n".join(f"- {pt}" for pt in enhanced_key_points) + "\n</ENHANCED_KEY_POINTS>\n\n"
            f"<EDITED_PREVIEW>\n{edited_preview}\n</EDITED_PREVIEW>\n\n"
            f"<FOUNDATIONAL_CONTEXT>\n{original_md[:4000]}\n</FOUNDATIONAL_CONTEXT>\n\n"
            f"<PARAMETERS>\n{json.dumps(parameters, indent=2)}\n</PARAMETERS>\n\n"
            f"Output the synthesized preview preserving all citation tags like [^src-1]."
        )

        # 1. Try Gemini
        if gemini_key and genai:
            try:
                client = genai.Client(api_key=gemini_key)
                for g_m in [gemini_model, "gemini-3.5-flash-lite", "gemini-flash-latest"]:
                    try:
                        resp = client.models.generate_content(
                            model=g_m,
                            contents=prompt,
                        )
                        if resp and resp.text:
                            return resp.text.strip()
                    except Exception:
                        continue
            except Exception as e:
                print(f"[branching_service] Gemini branch failed ({e}). Trying Groq fallback.")

        # 2. Try Groq
        if groq_key:
            try:
                from groq import Groq
                gclient = Groq(api_key=groq_key)
                for gm in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound"]:
                    try:
                        chat = gclient.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model=gm,
                            max_tokens=2500,
                            temperature=0.2,
                        )
                        txt = chat.choices[0].message.content.strip()
                        if "<think>" in txt and "</think>" in txt:
                            txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL).strip()
                        if txt:
                            return txt
                    except Exception:
                        continue
            except Exception as e:
                print(f"[branching_service] Groq branch failed ({e}).")

        # If Gemini call is unavailable or skipped, combine deterministically
        points_block = "\n".join(f"- {pt}" for pt in enhanced_key_points[:3])
        if points_block and points_block not in edited_preview:
            return f"{edited_preview}\n\n### Core Synthesis Points\n{points_block}"
        return edited_preview

branching_service = BranchingService()
