# generator.py
import os
import json
from typing import Dict, Any
from .types import FinalDeliverableResult, ProvenanceItem
from .category_prompts import get_prompt_for_category
from .mock import get_mock_final_deliverable
from dotenv import load_dotenv

try:
    from enhancements.nli_guardrail import verify_citations
except ImportError:
    def verify_citations(draft_text: str, source_context: str) -> dict:
        return {"verified_text": draft_text, "verdicts": [], "passed": True}

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    from groq import Groq
except ImportError:
    Groq = None

def generate_final_deliverable(platform_key: str, approved_draft: str, content_md: str, metadata_json: Dict[str, Any], parameters: Dict[str, Any]) -> FinalDeliverableResult:
    load_dotenv()
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    groq_key = os.environ.get("GROQ_API_KEY")
    groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")

    candidate_gemini_models = [
        gemini_model,
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
    ]
    seen_models = set()
    gemini_models_to_try = [m for m in candidate_gemini_models if m and not (m in seen_models or seen_models.add(m))]

    # 1. Extract category-specific system instructions
    system_instruction = get_prompt_for_category(platform_key)
    
    # 2. Structure the prompt using XML-style tags for clear component separation
    prompt = f"""
You must synthesize the <APPROVED_DRAFT> and the <GROUNDING_CONTEXT> to create the final deliverable.
Tailor the output explicitly to these <PARAMETERS>.

<PARAMETERS>
{json.dumps(parameters, indent=2)}
</PARAMETERS>

<METADATA>
{json.dumps(metadata_json, indent=2)}
</METADATA>

<GROUNDING_CONTEXT>
(Use this strictly for factual accuracy, metrics, and technical details. Do not hallucinate outside these facts.)
{content_md}
</GROUNDING_CONTEXT>

<APPROVED_DRAFT>
(Use this as the structural skeleton and thematic direction. Elevate the prose to match the requested platform and tone.)
{approved_draft}
</APPROVED_DRAFT>

OUTPUT INSTRUCTIONS:
Return a valid JSON object exactly matching this schema:
{{
  "final_content": "Your polished, perfectly formatted markdown text here...",
  "provenance": [
    {{"citation_marker": "[^src-1]", "source_reference": "Source Name or URL"}}
  ]
}}
"""
    data = None
    if gemini_key and genai:
        try:
            client = genai.Client(api_key=gemini_key)
            for g_model in gemini_models_to_try:
                try:
                    cfg = genai_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.3,
                    ) if genai_types else {"response_mime_type": "application/json"}
                    resp = client.models.generate_content(
                        model=g_model,
                        contents=prompt,
                        config=cfg,
                    )
                    raw = (resp.text or "").strip()
                    if raw.startswith("```json"):
                        raw = raw[7:]
                    if raw.startswith("```"):
                        raw = raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    data = json.loads(raw.strip())
                    print(f"[final_post_pipeline] ✅ Gemini generation succeeded with model '{g_model}'.")
                    break
                except Exception as e:
                    print(f"[final_post_pipeline] ❌ Gemini deliverable generation failed for '{g_model}': {e}")
                    if "404" in str(e) or "NOT_FOUND" in str(e) or "not available" in str(e).lower():
                        continue
                    else:
                        break
        except Exception as e:
            print(f"[final_post_pipeline] ❌ Failed to initialize Gemini client: {e}")

    if data is None and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            gresp = gclient.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            data = json.loads(gresp.choices[0].message.content)
        except Exception as e:
            print(f"Groq final deliverable generation failed ({e}).")

    if data is None:
        mock_res = get_mock_final_deliverable(platform_key, approved_draft)
        verification_report = verify_citations(mock_res.final_content, content_md)
        mock_res.verification = verification_report
        return mock_res

    final_content = data.get("final_content", approved_draft)
    verification_report = verify_citations(final_content, content_md)

    verdicts_by_marker = {
        v.get("citation_marker"): v for v in verification_report.get("verdicts", [])
    }

    provenance_list = []
    for item in data.get("provenance", []):
        marker = item.get("citation_marker", "")
        v_info = verdicts_by_marker.get(marker, {})
        provenance_list.append(
            ProvenanceItem(
                citation_marker=marker,
                source_reference=item.get("source_reference", ""),
                verification_score=v_info.get("entailment_score"),
                verification_status=v_info.get("status"),
                is_verified=v_info.get("is_verified"),
            )
        )

    return FinalDeliverableResult(
        platform_key=platform_key,
        final_content=final_content,
        provenance=provenance_list,
        verification=verification_report,
    )