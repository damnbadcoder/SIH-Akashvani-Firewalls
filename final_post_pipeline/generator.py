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
    from enhancements.anchor_relinker import relink_citations
except ImportError:
    def relink_citations(edited_text: str, original_text: str = ""):
        return edited_text, []

try:
    from enhancements.readability_scorer import score_readability
except ImportError:
    def score_readability(text: str, platform_key: str = "default") -> dict:
        return {"passed": True, "flesch_reading_ease": 60.0, "metrics": {}}

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


def _strip_element_by_class(text: str, tag: str, class_name: str) -> str:
    lower_text = text.lower()
    tag_open_prefix = f"<{tag}"
    class_str = class_name.lower()

    start_pos = 0
    while True:
        idx = lower_text.find(tag_open_prefix, start_pos)
        if idx == -1:
            break
        tag_end = lower_text.find(">", idx)
        if tag_end == -1:
            break
        tag_header = lower_text[idx:tag_end + 1]
        if class_str not in tag_header:
            start_pos = idx + 1
            continue

        depth = 1
        curr = tag_end + 1
        close_tag = f"</{tag}>"
        while depth > 0 and curr < len(text):
            if lower_text[curr:curr + len(tag_open_prefix)] == tag_open_prefix:
                depth += 1
                curr += len(tag_open_prefix)
            elif lower_text[curr:curr + len(close_tag)] == close_tag:
                depth -= 1
                if depth == 0:
                    break
                curr += len(close_tag)
            else:
                curr += 1

        if depth == 0:
            full_element = text[idx:curr + len(close_tag)]
            val_match = re.search(
                r'class="[^"]*flag-matched-value[^"]*"[^>]*>(.*?)</span>',
                full_element,
                re.IGNORECASE | re.DOTALL,
            )
            if val_match:
                replacement = val_match.group(1).strip()
            else:
                inner_content = text[tag_end + 1:curr]
                clean = re.sub(r"<[^>]+>", "", inner_content).strip()
                clean = re.sub(r"^\[(?:⚠️|SENSITIVE)[^:]*:\s*", "", clean)
                clean = re.sub(r"\]$", "", clean)
                replacement = clean.strip()

            text = text[:idx] + replacement + text[curr + len(close_tag):]
            lower_text = text.lower()
            start_pos = idx + len(replacement)
        else:
            start_pos = tag_end + 1

    return text


def strip_preview_wrappers(text: str) -> str:
    """
    Strips out interactive preview badges and resolves nested redactions for final release.
    Guarantees clean publication markdown without review UI inspection artifacts.
    """
    if not text:
        return ""
    # 1. Un-nest double redaction markers: [SENSITIVE: [REDACTED: X]] -> [REDACTED: X]
    text = re.sub(
        r"\[SENSITIVE:\s*\[REDACTED(?::\s*([^\]]+))?\]\]",
        lambda m: f"[REDACTED: {m.group(1)}]" if m.group(1) else "[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\[REDACTED:\s*\[REDACTED(?::\s*([^\]]+))?\]\]",
        lambda m: f"[REDACTED: {m.group(1)}]" if m.group(1) else "[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

    # 2. Strip review UI badges and HTML spans
    text = _strip_element_by_class(text, "span", "sensitive-flag-badge")
    text = _strip_element_by_class(text, "mark", "sensitive-flag-badge")

    # Red-colored style spans (from python scanner wrap_html=True)
    text = re.sub(
        r"<span[^>]*style=\"[^\"]*color:\s*red[^\"]*\"[^>]*>(.*?)</span>",
        r"\1",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Redacted pill badges: <span class="redacted-pill-badge">[REDACTED: ...]</span> -> [REDACTED: ...]
    text = re.sub(
        r"<span[^>]*class=\"[^\"]*redacted-pill-badge[^\"]*\"[^>]*>(.*?)</span>",
        r"\1",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 3. Strip standalone markdown review wrappers
    text = re.sub(
        r"\[SENSITIVE:\s*\[REDACTED(?::\s*([^\]]+))?\]\]",
        lambda m: f"[REDACTED: {m.group(1)}]" if m.group(1) else "[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[SENSITIVE:\s*(.*?)\]", r"\1", text, flags=re.IGNORECASE)

    # 4. Clean up classification banners
    text = re.sub(
        r"(\*{0,2}(?:CLASSIFICATION|TLP|TRAFFIC LIGHT PROTOCOL):\*{0,2}\s*)\[SENSITIVE:\s*([^\]]+)\]",
        r"\1\2",
        text,
        flags=re.IGNORECASE,
    )

    return text

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
        "gemini-3.6-flash",
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

    # Re-link citations if user edited the draft
    original_preview_draft = (
        metadata_json.get("original_preview_draft")
        or metadata_json.get("preview_draft")
        or parameters.get("original_preview_draft")
        or parameters.get("preview_draft")
        or ""
    )
    clean_approved_draft = strip_preview_wrappers(approved_draft)
    clean_original_draft = strip_preview_wrappers(original_preview_draft)
    safe_draft, relink_logs = relink_citations(clean_approved_draft, clean_original_draft)
    safe_draft = strip_preview_wrappers(safe_draft)

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
{safe_draft}
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
                        max_tokens=950,
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
            f"Grounding context:\n{content_md}\n\n"
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
        print("[final_post_pipeline] ⚠️ LLM deliverable generation unreached or failed. Using grounded approved draft fallback.")
        mock_res = get_mock_final_deliverable(platform_key, safe_draft)
        mock_res.final_content = strip_preview_wrappers(mock_res.final_content)
        verification_report = verify_citations(mock_res.final_content, content_md)
        mock_res.verification = verification_report
        mock_res.relinked_citations = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in relink_logs
        ]
        mock_res.readability = score_readability(mock_res.final_content, platform_key)
        return mock_res

    final_content = strip_preview_wrappers(data.get("final_content", safe_draft))
    verification_report = verify_citations(final_content, content_md)
    readability_report = score_readability(final_content, platform_key)

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
        relinked_citations=[
            m.model_dump() if hasattr(m, "model_dump") else m for m in relink_logs
        ],
        readability=readability_report,
    )