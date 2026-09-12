# generator.py
import os
import json
import re
from typing import Dict, Any, List, Optional
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

def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()
    if "<think>" in raw and "</think>" in raw:
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(raw[first_brace:last_brace+1])
        except Exception:
            pass
    return None


def generate_final_deliverable(platform_key: str, approved_draft: str, content_md: str, metadata_json: Dict[str, Any], parameters: Dict[str, Any]) -> FinalDeliverableResult:
    load_dotenv(override=True)
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    groq_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()

    candidate_gemini_models = [
        gemini_model,
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
    ]
    seen_models = set()
    gemini_models_to_try = [m for m in candidate_gemini_models if m and not (m in seen_models or seen_models.add(m))]

    candidate_groq_models = [
        groq_model,
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
    ]
    seen_gr = set()
    groq_models_to_try = [m for m in candidate_groq_models if m and not (m in seen_gr or seen_gr.add(m))]

    # 1. Extract category-specific system instructions
    system_instruction = get_prompt_for_category(platform_key)
    
    # 2. Structure the prompt using XML-style tags for clear component separation
    prompt = f"""
You must synthesize the <APPROVED_DRAFT> and the <GROUNDING_CONTEXT> to create the final deliverable for {platform_key.upper()}.
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
                    data = _extract_json_from_text(raw)
                    if data and "final_content" in data:
                        print(f"[final_post_pipeline] ✅ Gemini generation succeeded with model '{g_model}'.")
                        break
                    elif raw:
                        # LLM generated direct text rather than strict JSON
                        data = {"final_content": raw, "provenance": []}
                        print(f"[final_post_pipeline] ✅ Gemini direct text accepted with model '{g_model}'.")
                        break
                except Exception as e:
                    print(f"[final_post_pipeline] ❌ Gemini deliverable generation failed for '{g_model}': {e}")
                    continue
        except Exception as e:
            print(f"[final_post_pipeline] ❌ Failed to initialize Gemini client: {e}")

    if data is None and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            for g_model in groq_models_to_try:
                try:
                    gresp = gclient.chat.completions.create(
                        model=g_model,
                        messages=[
                            {"role": "system", "content": system_instruction + " Output valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3500,
                        temperature=0.3,
                    )
                    raw = gresp.choices[0].message.content.strip()
                    data = _extract_json_from_text(raw)
                    if data and "final_content" in data:
                        print(f"[final_post_pipeline] ✅ Groq deliverable succeeded with model '{g_model}'.")
                        break
                    elif raw:
                        data = {"final_content": raw, "provenance": []}
                        print(f"[final_post_pipeline] ✅ Groq direct text accepted with model '{g_model}'.")
                        break
                except Exception as e:
                    print(f"[final_post_pipeline] ❌ Groq deliverable generation failed for '{g_model}': {e}")
                    continue
        except Exception as e:
            print(f"[final_post_pipeline] ❌ Failed to initialize Groq client: {e}")

    # Fallback to direct prompt if structured formatting failed but keys are present
    if data is None and (gemini_key or groq_key):
        direct_prompt = (
            f"You are a cybersecurity expert. Write the final publication-ready deliverable for {platform_key}.\n"
            f"Grounding context:\n{content_md[:3500]}\n\n"
            f"Approved draft to polish:\n{approved_draft}\n\n"
            f"Preserve all citation markers like [^src-1]."
        )
        if gemini_key and genai:
            try:
                client = genai.Client(api_key=gemini_key)
                for m in gemini_models_to_try:
                    try:
                        resp = client.models.generate_content(model=m, contents=direct_prompt)
                        if resp and resp.text:
                            data = {"final_content": resp.text.strip(), "provenance": []}
                            print(f"[final_post_pipeline] ✅ Direct Gemini deliverable generation succeeded.")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

    if data is None:
        if gemini_key or groq_key:
            raise RuntimeError(
                f"Failed to generate final deliverable for '{platform_key}' using configured LLM models. "
                "Please verify model availability and network connection."
            )
        print("[final_post_pipeline] ⚠️ No API keys configured. Using get_mock_final_deliverable() fallback.")
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