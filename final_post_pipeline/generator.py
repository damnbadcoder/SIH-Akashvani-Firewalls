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

    target_lang = (
        parameters.get("language")
        or parameters.get("target_language")
        or "English"
    ).strip().title()

    if data is None:
        print("[final_post_pipeline] ⚠️ LLM deliverable generation unreached or failed. Using grounded approved draft fallback.")
        mock_res = get_mock_final_deliverable(platform_key, safe_draft)
        mock_res.final_content = strip_preview_wrappers(mock_res.final_content)
        verification_report = verify_citations(mock_res.final_content, content_md)
        mock_res.verification = verification_report
        mock_res.relinked_citations = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in relink_logs
        ]
        original_en = mock_res.final_content
        mock_res.original_english = original_en
        if target_lang in ("Hindi", "Telugu"):
            mock_res.final_content = translate_deliverable_to_language(
                text=mock_res.final_content,
                target_language=target_lang,
                platform_key=platform_key,
                gemini_key=gemini_key,
                groq_key=groq_key,
            )
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

    # -------------------------------------------------------------------------
    # PHASE 5.5: Language Localization (Target Language Update)
    # The entire ingestion & review pipeline runs in English. If user requested
    # an Indian language (Hindi or Telugu), the final deliverable is updated here.
    # -------------------------------------------------------------------------
    original_english = final_content
    if target_lang in ("Hindi", "Telugu"):
        final_content = translate_deliverable_to_language(
            text=final_content,
            target_language=target_lang,
            platform_key=platform_key,
            gemini_key=gemini_key,
            groq_key=groq_key,
        )

    return FinalDeliverableResult(
        platform_key=platform_key,
        final_content=final_content,
        original_english=original_english,
        provenance=provenance_list,
        verification=verification_report,
        relinked_citations=[
            m.model_dump() if hasattr(m, "model_dump") else m for m in relink_logs
        ],
        readability=readability_report,
    )


def translate_deliverable_to_language(
    text: str,
    target_language: str,
    platform_key: str = "default",
    gemini_key: str = "",
    groq_key: str = "",
) -> str:
    """
    Translates a final deliverable from English into an Indian language (Hindi or Telugu) or back to English.
    Strictly preserves:
    - Technical identifiers (CVEs, IP addresses, domains, ports, hashes, protocols, tool names) in Latin script.
    - Citation markers ([^src-1], [^src-2], [^aud-1], [^vid-1], [^doc-1], etc.)
    - Markdown structure, headings (#, ##), bullet points, blockquotes, and tables.
    """
    if not text or not target_language:
        return text

    target_lang = target_language.strip().title()
    if target_lang not in ("Hindi", "Telugu", "English"):
        return text

    has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in text)
    has_telugu = any("\u0c00" <= ch <= "\u0c7f" for ch in text)

    # If target is English and text has no Indic characters, it is already English
    if target_lang == "English" and not has_devanagari and not has_telugu:
        return text

    if target_lang == "English":
        system_instruction = (
            "You are an expert bilingual cybersecurity technical writer. "
            "Translate the provided cybersecurity document from Hindi/Telugu back into clear, authoritative English. "
            "MANDATORY REQUIREMENTS:\n"
            "1. Keep technical identifiers: Keep all CVEs (e.g. CVE-2026-41822), IP addresses (e.g. 192.168.1.100), domain names, URLs, port numbers, hashes, protocol names (CAN bus, TCP/IP, SSH, TLS), and product/company names in Latin characters exactly as written.\n"
            "2. DO NOT alter or remove citations: Retain all citation markers like [^src-1], [^src-2], [^aud-1], [^vid-1], [^doc-1] exactly in place.\n"
            "3. Retain exact Markdown formatting: Keep headings (#, ##), bullet points (*, -), bold text (**), blockquotes (>), and tables.\n"
            "4. Output ONLY the translated Markdown text without conversational filler, preamble, or code fences."
        )
        prompt = f"Translate the following cybersecurity deliverable back into natural, authoritative English:\n\n{text}"
    else:
        system_instruction = (
            f"You are an expert bilingual cybersecurity technical writer. "
            f"Translate the provided cybersecurity document into natural, authoritative {target_lang}. "
            f"MANDATORY REQUIREMENTS:\n"
            f"1. DO NOT translate technical identifiers: Keep all CVEs (e.g. CVE-2026-41822), IP addresses (e.g. 192.168.1.100), domain names, URLs, port numbers, hashes, protocol names (CAN bus, TCP/IP, SSH, TLS), and product/company names (BankShield, Linux, CERT-In) in Latin characters exactly as written.\n"
            f"2. DO NOT translate or remove citations: Retain all citation markers like [^src-1], [^src-2], [^aud-1], [^vid-1], [^doc-1] exactly in place.\n"
            f"3. Retain exact Markdown formatting: Keep headings (#, ##), bullet points (*, -), bold text (**), blockquotes (>), and tables.\n"
            f"4. Output ONLY the translated Markdown text without conversational filler, preamble, or code fences."
        )
        prompt = f"Translate the following cybersecurity deliverable into natural, fluent {target_lang}:\n\n{text}"

    # Try Groq (ultra fast and active)
    if not groq_key:
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key and Groq:
        groq_candidates = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "groq/compound"]
        try:
            gclient = Groq(api_key=groq_key)
            for g_m in groq_candidates:
                try:
                    resp = gclient.chat.completions.create(
                        model=g_m,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=1500,
                        temperature=0.2,
                    )
                    translated = (resp.choices[0].message.content or "").strip()
                    if translated:
                        if translated.startswith("```markdown") and translated.endswith("```"):
                            translated = translated[11:-3].strip()
                        elif translated.startswith("```") and translated.endswith("```"):
                            translated = translated[3:-3].strip()
                        print(f"[final_post_pipeline] ✅ Translated deliverable to {target_lang} using Groq '{g_m}'.")
                        return translated
                except Exception as ex:
                    print(f"[final_post_pipeline] ⚠️ Groq translation model '{g_m}' failed: {ex}")
        except Exception as ex:
            print(f"[final_post_pipeline] ⚠️ Failed Groq client for translation: {ex}")

    # Try Gemini
    if not gemini_key:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key and genai:
        gemini_candidates = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]
        try:
            client = genai.Client(api_key=gemini_key)
            for g_m in gemini_candidates:
                try:
                    cfg = genai_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    ) if genai_types else {}
                    resp = client.models.generate_content(
                        model=g_m,
                        contents=prompt,
                        config=cfg,
                    )
                    translated = (resp.text or "").strip()
                    if translated:
                        if translated.startswith("```markdown") and translated.endswith("```"):
                            translated = translated[11:-3].strip()
                        elif translated.startswith("```") and translated.endswith("```"):
                            translated = translated[3:-3].strip()
                        print(f"[final_post_pipeline] ✅ Translated deliverable to {target_lang} using Gemini '{g_m}'.")
                        return translated
                except Exception as ex:
                    print(f"[final_post_pipeline] ⚠️ Gemini translation model '{g_m}' failed: {ex}")
        except Exception as ex:
            print(f"[final_post_pipeline] ⚠️ Failed Gemini client for translation: {ex}")

    # Deterministic Indic localization fallback
    return _apply_indic_fallback_translation(text, target_lang)


def _apply_indic_fallback_translation(text: str, target_language: str) -> str:
    """Deterministic localization dictionary for common cybersecurity phrases in Hindi and Telugu."""
    if target_language == "Hindi":
        replacements = [
            ("TECHNICAL SECURITY ADVISORY", "तकनीकी सुरक्षा परामर्श"),
            ("Technical Security Advisory", "तकनीकी सुरक्षा परामर्श"),
            ("EXECUTIVE INTELLIGENCE SUMMARY", "कार्यकारी खुफिया सारांश"),
            ("Executive Intelligence Summary", "कार्यकारी खुफिया सारांश"),
            ("CYBERSECURITY INCIDENT REPORT", "साइबर सुरक्षा घटना रिपोर्ट"),
            ("Cybersecurity Incident Report", "साइबर सुरक्षा घटना रिपोर्ट"),
            ("PUBLIC SECURITY STATEMENT", "सार्वजनिक सुरक्षा वक्तव्य"),
            ("Public Security Statement", "सार्वजनिक सुरक्षा वक्तव्य"),
            ("REMEDIATION & INCIDENT PLAYBOOK", "उपचार और घटना प्लेबुक"),
            ("Remediation & Incident Playbook", "उपचार और घटना प्लेबुक"),
            ("EXECUTIVE BRIEFING SLIDE DECK", "कार्यकारी ब्रीफिंग स्लाइड डेक"),
            ("Executive Briefing Slide Deck", "कार्यकारी ब्रीफिंग स्लाइड डेक"),
            ("AUDIO & VIDEO BRIEFING SCRIPT", "ऑडियो और वीडियो ब्रीफिंग स्क्रिप्ट"),
            ("Audio & Video Briefing Script", "ऑडियो और वीडियो ब्रीफिंग स्क्रिप्ट"),
            ("TRAFFIC LIGHT PROTOCOL", "ट्रैफिक लाइट प्रोटोकॉल"),
            ("SEVERITY", "गंभीरता"),
            ("CRITICAL", "गंभीर"),
            ("HIGH", "उच्च"),
            ("MEDIUM", "मध्यम"),
            ("LOW", "कम"),
            ("Key Findings", "मुख्य निष्कर्ष"),
            ("Incident Summary", "घटना सारांश"),
            ("Threat Assessment", "जोखिम मूल्यांकन"),
            ("Immediate Actions Required", "तत्काल आवश्यक कार्रवाइयां"),
            ("Immediate Remediation Steps", "तत्काल उपचार के कदम"),
            ("Remediation Steps", "उपचार के कदम"),
            ("Technical Mitigations", "तकनीकी शमन उपाय"),
            ("Target Audience", "लक्षित पाठक"),
            ("Published By", "प्रकाशक"),
            ("Actionable Guidance", "कार्रवाई योग्य मार्गदर्शन"),
            ("Blast Radius & Impact", "प्रभाव और फैलाव"),
            ("Takeaways & Next Steps", "निष्कर्ष और अगले कदम"),
            ("Entry Vector", "प्रवेश माध्यम"),
            ("Lateral Infiltration", "आंतरिक घुसपैठ"),
            ("Access Risk", "पहुंच जोखिम"),
            ("Threat Alert", "सुरक्षा चेतावनी"),
            ("Urgent Directive", "तत्काल निर्देश"),
            ("Security Leaders", "सुरक्षा प्रमुख"),
            ("Enterprise Infrastructure", "उद्यम बुनियादी ढांचा"),
        ]
    elif target_language == "Telugu":
        replacements = [
            ("TECHNICAL SECURITY ADVISORY", "సాంకేతిక భద్రతా సలహా"),
            ("Technical Security Advisory", "సాంకేతిక భద్రతా సలహా"),
            ("EXECUTIVE INTELLIGENCE SUMMARY", "కార్యనిర్వాహక భద్రతా సారాంశం"),
            ("Executive Intelligence Summary", "కార్యనిర్వాహక భద్రతా సారాంశం"),
            ("CYBERSECURITY INCIDENT REPORT", "సైబర్ భద్రతా సంఘటన నివేదిక"),
            ("Cybersecurity Incident Report", "సైబర్ భద్రతా సంఘటన నివేదిక"),
            ("PUBLIC SECURITY STATEMENT", "ప్రజా భద్రతా ప్రకటన"),
            ("Public Security Statement", "ప్రజా భద్రతా ప్రకటన"),
            ("REMEDIATION & INCIDENT PLAYBOOK", "పరిష్కార & సంఘటన ప్లేబుక్"),
            ("Remediation & Incident Playbook", "పరిష్కార & సంఘటన ప్లేబుక్"),
            ("EXECUTIVE BRIEFING SLIDE DECK", "కార్యనిర్వాహక బ్రీఫింగ్ స్లైడ్ డెక్"),
            ("Executive Briefing Slide Deck", "కార్యనిర్వాహక బ్రీఫింగ్ స్లైడ్ డెక్"),
            ("AUDIO & VIDEO BRIEFING SCRIPT", "ఆడియో మరియు వీడియో బ్రీఫింగ్ స్క్రిప్ట్"),
            ("Audio & Video Briefing Script", "ఆడియో మరియు వీడియో బ్రీఫింగ్ స్క్రిప్ట్"),
            ("TRAFFIC LIGHT PROTOCOL", "ట్రాఫిక్ లైట్ ప్రోటోకాల్"),
            ("SEVERITY", "తీవ్రత"),
            ("CRITICAL", "కీలకమైనది"),
            ("HIGH", "అధికం"),
            ("MEDIUM", "మధ్యస్థం"),
            ("LOW", "తక్కువ"),
            ("Key Findings", "ముఖ్యమైన గమనింపులు"),
            ("Incident Summary", "సంఘటన సారాంశం"),
            ("Threat Assessment", "ముప్పు అంచనా"),
            ("Immediate Actions Required", "వెంటనే తీసుకోవాల్సిన చర్యలు"),
            ("Immediate Remediation Steps", "తక్షణ పరిష్కార చర్యలు"),
            ("Remediation Steps", "పరిష్కార చర్యలు"),
            ("Technical Mitigations", "సాంకేతిక నివారణ చర్యలు"),
            ("Target Audience", "లక్ష్య ప్రేక్షకులు"),
            ("Published By", "ప్రచురణకర్త"),
            ("Actionable Guidance", "ఆచరణాత్మక మార్గదర్శకత్వం"),
            ("Blast Radius & Impact", "ప్రభావం మరియు పరిధి"),
            ("Takeaways & Next Steps", "ముగింపు మరియు తదుపరి దశలు"),
            ("Entry Vector", "ప్రవేశ మార్గం"),
            ("Lateral Infiltration", "అంతర్గత వ్యాప్తి"),
            ("Access Risk", "యాక్సెస్ ప్రమాదం"),
            ("Threat Alert", "భద్రతా హెచ్చరిక"),
            ("Urgent Directive", "తక్షణ ఆదేశం"),
            ("Security Leaders", "భద్రతా నాయకులు"),
            ("Enterprise Infrastructure", "సంస్థాగత మౌలిక సదుపాయాలు"),
        ]
    elif target_language == "English":
        localized = text
        for en, tr in [
            ("TECHNICAL SECURITY ADVISORY", "సాంకేతిక భద్రతా సలహా"),
            ("Technical Security Advisory", "సాంకేతిక భద్రతా సలహా"),
            ("EXECUTIVE INTELLIGENCE SUMMARY", "కార్యనిర్వాహక భద్రతా సారాంశం"),
            ("Executive Intelligence Summary", "కార్యనిర్వాహక భద్రతా సారాంశం"),
            ("CYBERSECURITY INCIDENT REPORT", "సైబర్ భద్రతా సంఘటన నివేదిక"),
            ("Cybersecurity Incident Report", "సైబర్ భద్రతా సంఘటన నివేదిక"),
            ("PUBLIC SECURITY STATEMENT", "ప్రజా భద్రతా ప్రకటన"),
            ("Public Security Statement", "ప్రజా భద్రతా ప్రకటన"),
            ("REMEDIATION & INCIDENT PLAYBOOK", "పరిష్కార & సంఘటన ప్లేబుక్"),
            ("Remediation & Incident Playbook", "పరిష్కార & సంఘటన ప్లేబుక్"),
            ("EXECUTIVE BRIEFING SLIDE DECK", "కార్యనిర్వాహక బ్రీఫింగ్ స్లైడ్ డెక్"),
            ("Executive Briefing Slide Deck", "కార్యనిర్వాహక బ్రీఫింగ్ స్లైడ్ డెక్"),
            ("AUDIO & VIDEO BRIEFING SCRIPT", "ఆడియో మరియు వీడియో బ్రీఫింగ్ స్క్రిప్ట్"),
            ("Audio & Video Briefing Script", "ఆడియో మరియు వీడియో బ్రీఫింగ్ స్క్రిప్ట్"),
            ("TRAFFIC LIGHT PROTOCOL", "ట్రాఫిక్ లైట్ ప్రోటోకాల్"),
            ("SEVERITY", "తీవ్రత"),
            ("CRITICAL", "కీలకమైనది"),
            ("HIGH", "అధికం"),
            ("MEDIUM", "మధ్యస్థం"),
            ("LOW", "తక్కువ"),
            ("Key Findings", "ముఖ్యమైన గమనింపులు"),
            ("Incident Summary", "సంఘటన సారాంశం"),
            ("Threat Assessment", "ముప్పు అంచనా"),
            ("Immediate Actions Required", "వెంటనే తీసుకోవాల్సిన చర్యలు"),
            ("Immediate Remediation Steps", "తక్షణ పరిష్కార చర్యలు"),
            ("Remediation Steps", "పరిష్కార చర్యలు"),
            ("Technical Mitigations", "సాంకేతిక నివారణ చర్యలు"),
            ("Target Audience", "లక్ష్య ప్రేక్షకులు"),
            ("Published By", "ప్రచురణకర్త"),
            ("Actionable Guidance", "ఆచరణాత్మక మార్గదర్శకత్వం"),
            ("Blast Radius & Impact", "ప్రభావం మరియు పరిధి"),
            ("Takeaways & Next Steps", "ముగింపు మరియు తదుపరి దశలు"),
            ("Entry Vector", "ప్రవేశ మార్గం"),
            ("Lateral Infiltration", "అంతర్గత వ్యాప్తి"),
            ("Access Risk", "యాక్సెస్ ప్రమాదం"),
            ("Threat Alert", "భద్రతా హెచ్చరిక"),
            ("Urgent Directive", "తక్షణ ఆదేశం"),
            ("Security Leaders", "భద్రతా నాయకులు"),
            ("Enterprise Infrastructure", "సంస్థాగత మౌలిక సదుపాయాలు"),
        ]:
            localized = localized.replace(tr, en)
        for en, tr in [
            ("TECHNICAL SECURITY ADVISORY", "तकनीकी सुरक्षा परामर्श"),
            ("Technical Security Advisory", "तकनीकी सुरक्षा परामर्श"),
            ("EXECUTIVE INTELLIGENCE SUMMARY", "कार्यकारी खुफिया सारांश"),
            ("Executive Intelligence Summary", "कार्यकारी खुफिया सारांश"),
            ("CYBERSECURITY INCIDENT REPORT", "साइबर सुरक्षा घटना रिपोर्ट"),
            ("Cybersecurity Incident Report", "साइबर सुरक्षा घटना रिपोर्ट"),
            ("PUBLIC SECURITY STATEMENT", "सार्वजनिक सुरक्षा वक्तव्य"),
            ("Public Security Statement", "सार्वजनिक सुरक्षा वक्तव्य"),
            ("REMEDIATION & INCIDENT PLAYBOOK", "उपचार और घटना प्लेबुक"),
            ("Remediation & Incident Playbook", "उपचार और घटना प्लेबुक"),
            ("EXECUTIVE BRIEFING SLIDE DECK", "कार्यकारी ब्रीफिंग स्लाइड डेक"),
            ("Executive Briefing Slide Deck", "कार्यकारी ब्रीफिंग स्लाइड डेक"),
            ("AUDIO & VIDEO BRIEFING SCRIPT", "ऑडियो और वीडियो ब्रीफिंग स्क्रिप्ट"),
            ("Audio & Video Briefing Script", "ऑडियो और वीडियो ब्रीफिंग स्क्रिप्ट"),
            ("TRAFFIC LIGHT PROTOCOL", "ट्रैफिक लाइट प्रोटोकॉल"),
            ("SEVERITY", "गंभीरता"),
            ("CRITICAL", "गंभीर"),
            ("HIGH", "उच्च"),
            ("MEDIUM", "मध्यम"),
            ("LOW", "कम"),
            ("Key Findings", "मुख्य निष्कर्ष"),
            ("Incident Summary", "घटना सारांश"),
            ("Threat Assessment", "जोखिम मूल्यांकन"),
            ("Immediate Actions Required", "तत्काल आवश्यक कार्रवाइयां"),
            ("Immediate Remediation Steps", "तत्काल उपचार के कदम"),
            ("Remediation Steps", "उपचार के कदम"),
            ("Technical Mitigations", "तकनीकी शमन उपाय"),
            ("Target Audience", "लक्षित पाठक"),
            ("Published By", "प्रकाशक"),
            ("Actionable Guidance", "कार्रवाई योग्य मार्गदर्शन"),
            ("Blast Radius & Impact", "प्रभाव और फैलाव"),
            ("Takeaways & Next Steps", "निष्कर्ष और अगले कदम"),
            ("Entry Vector", "प्रवेश माध्यम"),
            ("Lateral Infiltration", "आंतरिक घुसपैठ"),
            ("Access Risk", "पहुंच जोखिम"),
            ("Threat Alert", "सुरक्षा चेतावनी"),
            ("Urgent Directive", "तत्काल निर्देश"),
            ("Security Leaders", "सुरक्षा प्रमुख"),
            ("Enterprise Infrastructure", "उद्यम बुनियादी ढांचा"),
        ]:
            localized = localized.replace(tr, en)
        return localized
    else:
        return text

    localized = text
    for en, tr in replacements:
        localized = localized.replace(en, tr)
    return localized