import os
import json
import traceback
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from .types import (
    MultiPreviewResult, 
    PlatformPreview, 
    SensitiveDataFlag,
    OutputType,
    LinkedInPreviewContent,
    SocialThreadPreviewContent,
    AdvisoryPreviewContent,
    ExecSummaryPreviewContent,
    IncidentReportPreviewContent,
    PressReleasePreviewContent,
    SlideDeckPreviewContent,
    VideoScriptPreviewContent,
    PlaybookPreviewContent,
)
try:
    from enhancements.sensitivity_checker import scan_and_redact
except ImportError:
    def scan_and_redact(text: str, is_organization: bool = False):
        return text, []
from .mock import get_mock_previews
from .renderers import RENDERERS

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

# Platform-specific system prompts for structured generation
PLATFORM_PROMPTS = {
    OutputType.LINKEDIN_POST: """
You are a senior cybersecurity content strategist writing a LinkedIn post for CISOs, SecOps managers, and engineering leaders.
OUTPUT FORMAT: Return ONLY valid JSON matching the LinkedInPreviewContent schema.

REQUIREMENTS:
- hook: ONE punchy opening line (< 150 chars) that creates urgency for leadership. Directly reference key findings/frameworks from the source material. Never output placeholder phrases like "Attention-grabbing opening line".
- threat_context: 2-3 substantive sentences summarizing the campaign, actor, framework, or event from the source material.
- key_insights: EXACTLY 3 insights directly grounded in the source - each a complete sentence, business-relevant.
- actionable_takeaways: EXACTLY 3 actions - specific, measurable, for SecOps/IT managers and engineering architects.
- discussion_prompt: ONE engaging question for comments directly tied to the topic.
- hashtags: 3-5 relevant tags (e.g., #CyberSecurity #CISO #AutomotiveSecurity #DevSecOps)
- citations_used: List of citation markers like ["[^src-1]", "[^src-2]"] used in the content

STYLE: Professional, authoritative, zero fluff. No placeholder bullet text. Write concrete, actionable sentences.
""",

    OutputType.SOCIAL_THREAD: """
You are a threat intelligence analyst writing a 5-tweet thread (X/Twitter) for the InfoSec community.
OUTPUT FORMAT: Return ONLY valid JSON matching the SocialThreadPreviewContent schema.

REQUIREMENTS:
- hook_tweet: Tweet 1 - URGENT alert + hook (<=280 chars). Must include 🚨 or 🧵
- exploit_tweet: Tweet 2 - How the exploit works in plain English (<=280 chars)
- ioc_tweet: Tweet 3 - Key IOCs defenders can check NOW (<=280 chars). Include 1-2 concrete indicators
- mitigation_tweet: Tweet 4 - 3 immediate defense steps (<=280 chars). Numbered 1️⃣ 2️⃣ 3️⃣
- wrapup_tweet: Tweet 5 - Official advisory link placeholder + CTA + hashtags (<=280 chars)
- all_tweets: Array of all 5 tweets in order
- citations_used: Citation markers used

STYLE: Technical but accessible. Thread emojis (🧵 👇 🔗). Each tweet standalone but connected.
""",

    OutputType.ADVISORY: """
You are a CERT analyst writing a formal Technical Security Advisory (CISA/CERT style).
OUTPUT FORMAT: Return ONLY valid JSON matching the AdvisoryPreviewContent schema.

REQUIREMENTS:
- tl_protocol: "TLP:AMBER+STRICT" or "TLP:RED" or "TLP:GREEN"
- severity: "CRITICAL" | "HIGH" | "MEDIUM"
- cvss_score: Float (e.g., 9.1) if CVE available, else null
- cve_ids: Array of CVE IDs mentioned in source (e.g., ["CVE-2026-41822"])
- threat_actor: Attributed group name if in source, else null
- affected_systems: Specific platforms/versions from source
- executive_summary: 2-3 sentences for leadership - impact + urgency
- technical_analysis: Detailed exploit chain with MITRE ATT&CK technique IDs (T1190, T1059, etc.)
- iocs: Array of objects: {"type": "IPv4|Domain|Hash|CVE", "indicator": "...", "context": "...", "action": "block|monitor|patch"}
- mitigations: Prioritized numbered steps (1. Immediate, 2. Short-term, 3. Strategic)
- cert_reporting: Official reporting contact if applicable
- citations_used: All citation markers used

STYLE: Formal, precise, actionable. Zero marketing language.
""",

    OutputType.EXEC_SUMMARY: """
You are a CISO's chief of staff writing an Executive Brief for the Board.
OUTPUT FORMAT: Return ONLY valid JSON matching the ExecSummaryPreviewContent schema.

REQUIREMENTS:
- bluf: ONE sentence - Bottom Line Up Front. What happened + business impact.
- situation: 2-3 sentences - operational baseline & threat context
- complication: Business impact - downtime risk, regulatory, brand, legal
- solution: What SOC did - containment, credentials rotated, patches deployed
- strategic_recommendations: 3-4 items - budget, tooling, headcount, policy decisions needed
- citations_used: Citation markers used

STYLE: Executive-ready. No deep technical jargon. Business risk vocabulary.
""",

    OutputType.INCIDENT_REPORT: """
You are a DFIR lead writing an Incident Triage & Forensic Report.
OUTPUT FORMAT: Return ONLY valid JSON matching the IncidentReportPreviewContent schema.

REQUIREMENTS:
- incident_id: "INC-2026-XXXX" format
- status: "CONTAINED" | "UNDER TRIAGE" | "RESOLVED"
- severity: "Tier 1 High" | "Tier 2 Medium" | "Tier 3 Low"
- timeline: Array of {"time": "HH:MM:SS UTC", "event": "..."} - at least 4 entries
- root_cause: Specific vulnerability + injection vector
- blast_radius: Affected hosts, services, credentials - be specific
- corrective_actions: Array of {"action": "...", "status": "complete|in-progress|pending", "owner": "team"}
- citations_used: Citation markers used

STYLE: Forensic precision. UTC timestamps. Evidence-based.
""",

    OutputType.PRESS_RELEASE: """
You are a security communications lead writing a Public Security Advisory.
OUTPUT FORMAT: Return ONLY valid JSON matching the PressReleasePreviewContent schema.

REQUIREMENTS:
- dateline: "CITY — DATE" (e.g., "NEW DELHI — October 12, 2026")
- headline: Reassuring, factual headline
- customer_impact: Explicit "No customer data compromised" or specific impact
- proactive_measures: 3-4 engineering actions taken
- user_guidance: 3-4 safe practices for users
- media_contact: Email/phone for press
- citations_used: Citation markers used

STYLE: Transparent, reassuring, factual. No speculation.
""",

    OutputType.SLIDE_DECK: """
You are a security architect creating a board presentation slide deck.
OUTPUT FORMAT: Return ONLY valid JSON matching the SlideDeckPreviewContent schema.

REQUIREMENTS:
- slides: Array of slide objects with:
  * title: Slide title
  * type: "TITLE_SLIDE" | "TWO_COLUMN" | "TIMELINE" | "CONCLUSION" | "METRICS"
  * key_points: Array of 3-5 bullet points
  * speaker_notes: Talking points for presenter
- citations_used: Citation markers used

SLIDES NEEDED (4-5):
1. TITLE_SLIDE: Executive Overview
2. TWO_COLUMN: Attack Anatomy (left: technical, right: MITRE mapping)
3. TIMELINE: Remediation Roadmap
4. CONCLUSION: Strategic Recommendations
5. Optional METRICS: Dwell time, MTTD, MTTR
""",

    OutputType.VIDEO_SCRIPT: """
You are a threat intelligence video producer writing a 90-second narration script.
OUTPUT FORMAT: Return ONLY valid JSON matching the VideoScriptPreviewContent schema.

REQUIREMENTS:
- runtime_seconds: 90
- scenes: Array of 4 scenes with:
  * scene: "Scene 1 (0:00-0:15)" etc.
  * visual: What's on screen (threat map, animation, checkmarks, logo)
  * narrator: Voice-over script (conversational, urgent but calm)
- citations_used: Citation markers used

SCENES:
1. Hook + Alert (0:00-0:15)
2. Technical Breakdown (0:15-0:45)
3. Defense Directives (0:45-1:15)
4. Conclusion + Resources (1:15-1:30)
""",

    OutputType.PLAYBOOK: """
You are a SOC manager writing an Incident Response Remediation Playbook.
OUTPUT FORMAT: Return ONLY valid JSON matching the PlaybookPreviewContent schema.

REQUIREMENTS:
- playbook_code: "PB-SEC-XX" format
- stages: Array of 4 stages:
  * Stage 1: Identification & Verification (queries, IOC validation)
  * Stage 2: Immediate Containment (isolation, firewall rules, session revocation)
  * Stage 3: Eradication & Recovery (re-image, hash verification, key rotation)
  * Stage 4: Post-Incident (log audit, detection rules, timeline report)
  Each stage: {"stage": 1, "title": "...", "steps": [...], "commands": [...]}
- citations_used: Citation markers used

STYLE: Operational, runbook-ready. Bash commands where applicable.
""",
}

def build_structured_prompt(selected_outputs: List[str], parameters: Dict[str, Any], content_md: str, metadata_json: Dict[str, Any]) -> str:
    """Build a prompt that asks for structured JSON for each selected output type."""
    
    output_instructions = []
    for out in selected_outputs:
        if out in PLATFORM_PROMPTS:
            output_instructions.append(f"=== {out.upper()} ===\n{PLATFORM_PROMPTS[out]}")
    
    outputs_schema = ", ".join(selected_outputs)
    
    return f"""You are an expert cybersecurity content synthesis engine.
Generate structured preview drafts for these output types: {outputs_schema}

TARGET AUDIENCE & PARAMETERS:
{json.dumps(parameters, indent=2)}

PRIMARY SOURCE MATERIAL (Extract all facts, metrics, actors, frameworks directly from here):
{content_md}

METADATA / ANCHORS (JSON):
{json.dumps(metadata_json, indent=2)}

CRITICAL INSTRUCTIONS:
1. Ground the content 100% in the PRIMARY SOURCE MATERIAL provided above. If the source discusses automotive cybersecurity (e.g., CERT-In SAMVAAD 2025, in-vehicle communications, ECU telemetry, compliance), draft concrete material about that exact topic.
2. DO NOT output placeholder phrases, templates, or instructions (e.g., DO NOT write "Attention-grabbing opening line", "3 bullet points", or generic boilerplate). Write REAL, substantive, copy-ready drafts.
3. For EACH output type, generate a JSON object matching its exact schema.
4. Return a single JSON object with keys = output_type, values = structured content object.
5. Include "citations_used" array in each with markers like "[^src-1]".
6. Extract key facts from source and include in response as "extracted_facts" array of strings.
7. Include metadata anchors as "metadata_anchors" object.

{chr(10).join(output_instructions)}

RETURN ONLY STRICT VALID JSON. NO MARKDOWN WRAPPERS. NO EXPLANATION.
"""


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()
    if "<think>" in raw and "</think>" in raw:
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Strip markdown fencing ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    # Extract outer JSON object {...}
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(raw[first_brace:last_brace+1])
        except Exception:
            pass
    return None


def _find_output_data(data: Dict[str, Any], key: str) -> Any:
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    norm_map = {str(k).lower().replace("_", "").replace("-", ""): v for k, v in data.items()}
    target = key.lower().replace("_", "").replace("-", "")
    if target in norm_map:
        return norm_map[target]
    for sub in ["previews", "outputs", "results", "data"]:
        if sub in data and isinstance(data[sub], dict):
            found = _find_output_data(data[sub], key)
            if found is not None:
                return found
    aliases = {
        "linkedin_post": ["linkedin", "linkedinpost"],
        "social_thread": ["twitter", "x", "thread", "socialthread"],
        "exec_summary": ["executive_summary", "executivesummary", "summary", "brief"],
        "slide_deck": ["presentation", "slides", "slidedeck"],
        "video_script": ["video", "script", "videoscript"],
        "playbook": ["infographic", "runbook", "playbook_guide"],
    }
    for alias in aliases.get(key, []):
        t = alias.lower().replace("_", "").replace("-", "")
        if t in norm_map:
            return norm_map[t]
    return None


def _generate_single_preview_llm(
    key: str,
    content_md: str,
    parameters: Dict[str, Any],
    is_organization: bool,
    gemini_key: str,
    gemini_models: List[str],
    groq_key: str,
    groq_models: List[str]
) -> Optional[PlatformPreview]:
    """Generates preview for a single output type directly via LLM if batch parsing missed it."""
    prompt = (
        f"You are an expert cybersecurity content strategist.\n"
        f"Generate a publication-ready draft for: {key.upper()}.\n"
        f"Tone & Parameters: {json.dumps(parameters)}\n\n"
        f"SOURCE MATERIAL:\n{content_md[:4000]}\n\n"
        f"Requirements: Ground content strictly in source material. Preserve citation tags like [^src-1]. "
        f"Provide comprehensive, high-quality, professional markdown formatted content."
    )
    draft_text = ""
    # Try Gemini
    if gemini_key and genai:
        try:
            client = genai.Client(api_key=gemini_key)
            for m in gemini_models:
                try:
                    resp = client.models.generate_content(model=m, contents=prompt)
                    if resp and resp.text:
                        draft_text = resp.text.strip()
                        print(f"[preview_pipeline] ✅ Single preview '{key}' generated with Gemini '{m}'.")
                        break
                except Exception as ge:
                    print(f"[preview_pipeline] Note: single preview '{key}' with '{m}' failed: {ge}")
        except Exception:
            pass

    # Try Groq
    if not draft_text and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            for gm in groq_models:
                try:
                    chat = gclient.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=gm,
                        max_tokens=2000,
                        temperature=0.2,
                    )
                    txt = chat.choices[0].message.content.strip()
                    if "<think>" in txt and "</think>" in txt:
                        txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL).strip()
                    if txt:
                        draft_text = txt
                        print(f"[preview_pipeline] ✅ Single preview '{key}' generated with Groq '{gm}'.")
                        break
                except Exception as gre:
                    print(f"[preview_pipeline] Note: single preview '{key}' with Groq '{gm}' failed: {gre}")
        except Exception:
            pass

    if not draft_text:
        return None

    flags = []
    if is_organization:
        draft_text, flags = scan_and_redact(draft_text, is_organization=True)

    citations_used = re.findall(r"\[\^[^\]]+\]", draft_text) or ["[^-src-1]"]
    return PlatformPreview(
        platform_key=key,
        display_name=key.replace("_", " ").title(),
        draft_title=f"{key.replace('_', ' ').title()} Preview",
        draft_content=draft_text,
        structured_content=None,
        citations_used=citations_used,
        sensitive_flags=flags,
    )


def generate_previews(content_md: str, metadata_json: Dict[str, Any], selected_outputs: List[str], parameters: Dict[str, Any], is_organization: bool = False) -> MultiPreviewResult:
    load_dotenv(override=True)
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    groq_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    
    prompt = build_structured_prompt(selected_outputs, parameters, content_md, metadata_json)
    data = None

    candidate_gemini_models = [
        gemini_model,
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
    ]
    seen_g = set()
    gemini_models_to_try = [m for m in candidate_gemini_models if m and not (m in seen_g or seen_g.add(m))]

    candidate_groq_models = [
        groq_model,
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
    ]
    seen_gr = set()
    groq_models_to_try = [m for m in candidate_groq_models if m and not (m in seen_gr or seen_gr.add(m))]

    if gemini_key and genai:
        try:
            client = genai.Client(api_key=gemini_key)
            for g_model in gemini_models_to_try:
                try:
                    print(f"[preview_pipeline] Generating previews via Gemini model '{g_model}'...")
                    cfg = genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ) if genai_types else {"response_mime_type": "application/json"}
                    resp = client.models.generate_content(
                        model=g_model,
                        contents=prompt,
                        config=cfg,
                    )
                    raw = (resp.text or "").strip()
                    data = _extract_json_from_text(raw)
                    if data:
                        print(f"[preview_pipeline] ✅ Gemini generation succeeded with model '{g_model}'.")
                        break
                    else:
                        print(f"[preview_pipeline] ⚠️ Gemini returned text but could not parse JSON: {raw[:150]}...")
                except Exception as e:
                    print(f"[preview_pipeline] ❌ Gemini preview generation failed for '{g_model}': {e}")
                    continue
        except Exception as e:
            print(f"[preview_pipeline] ❌ Failed to initialize Gemini client: {e}")

    if data is None and groq_key and Groq:
        try:
            gclient = Groq(api_key=groq_key)
            for g_model in groq_models_to_try:
                try:
                    print(f"[preview_pipeline] Attempting Groq with model '{g_model}'...")
                    gresp = gclient.chat.completions.create(
                        model=g_model,
                        messages=[
                            {"role": "system", "content": "You are an expert cybersecurity threat intelligence analyst. You output strictly valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3000,
                        temperature=0.2,
                    )
                    raw = gresp.choices[0].message.content.strip()
                    data = _extract_json_from_text(raw)
                    if data:
                        print(f"[preview_pipeline] ✅ Groq generation succeeded with model '{g_model}'.")
                        break
                except Exception as e:
                    print(f"[preview_pipeline] ❌ Groq preview generation failed for '{g_model}': {e}")
                    continue
        except Exception as e:
            print(f"[preview_pipeline] ❌ Failed to initialize Groq client: {e}")

    result_previews = {}
    extracted_facts = []
    metadata_anchors = {}

    if data:
        extracted_facts = data.get("extracted_facts", [])
        metadata_anchors = data.get("metadata_anchors", {})

        for key in selected_outputs:
            structured = _find_output_data(data, key)
            if structured is None:
                continue

            flags = []
            citations = []
            if isinstance(structured, dict):
                citations = structured.get("citations_used", [])
                renderer = RENDERERS.get(key)
                if renderer:
                    draft_content = renderer(structured)
                else:
                    draft_content = json.dumps(structured, indent=2)
            elif isinstance(structured, str):
                draft_content = structured
                citations = re.findall(r"\[\^[^\]]+\]", draft_content) or ["[^-src-1]"]
            else:
                draft_content = str(structured)

            if is_organization:
                draft_content, flags = scan_and_redact(draft_content, is_organization=True)

            structured_obj = None
            if isinstance(structured, dict):
                try:
                    if key == OutputType.LINKEDIN_POST:
                        structured_obj = LinkedInPreviewContent(**structured)
                    elif key == OutputType.SOCIAL_THREAD:
                        structured_obj = SocialThreadPreviewContent(**structured)
                    elif key == OutputType.ADVISORY:
                        structured_obj = AdvisoryPreviewContent(**structured)
                    elif key == OutputType.EXEC_SUMMARY:
                        structured_obj = ExecSummaryPreviewContent(**structured)
                    elif key == OutputType.INCIDENT_REPORT:
                        structured_obj = IncidentReportPreviewContent(**structured)
                    elif key == OutputType.PRESS_RELEASE:
                        structured_obj = PressReleasePreviewContent(**structured)
                    elif key == OutputType.SLIDE_DECK:
                        structured_obj = SlideDeckPreviewContent(**structured)
                    elif key == OutputType.VIDEO_SCRIPT:
                        structured_obj = VideoScriptPreviewContent(**structured)
                    elif key == OutputType.PLAYBOOK:
                        structured_obj = PlaybookPreviewContent(**structured)
                except Exception as e:
                    structured_obj = None

            result_previews[key] = PlatformPreview(
                platform_key=key,
                display_name=key.replace("_", " ").title(),
                draft_title=f"{key.replace('_', ' ').title()} Preview",
                draft_content=draft_content,
                structured_content=structured_obj,
                citations_used=citations,
                sensitive_flags=flags
            )

    # If any selected output was missing from structured batch response, generate with LLM individually
    for key in selected_outputs:
        if key not in result_previews and (gemini_key or groq_key):
            print(f"[preview_pipeline] Individually synthesizing missing preview '{key}' with live LLM...")
            single_preview = _generate_single_preview_llm(
                key=key,
                content_md=content_md,
                parameters=parameters,
                is_organization=is_organization,
                gemini_key=gemini_key,
                gemini_models=gemini_models_to_try,
                groq_key=groq_key,
                groq_models=groq_models_to_try,
            )
            if single_preview:
                result_previews[key] = single_preview

    # If still empty (e.g. no API keys configured or all calls exhausted), fallback to mock only if no keys
    if not result_previews:
        if gemini_key or groq_key:
            raise RuntimeError(
                "Failed to generate previews using configured LLM models (Gemini / Groq). "
                "Please verify model availability and network access."
            )
        print("[preview_pipeline] ⚠️ No API keys configured. Using get_mock_previews() fallback.")
        return get_mock_previews(content_md, selected_outputs, is_organization)

    return MultiPreviewResult(
        is_organization=is_organization,
        previews=result_previews,
        source_summary=(data.get("source_summary", "") if data else "") or "Generated from threat intelligence source material using live LLMs.",
        extracted_facts=extracted_facts,
        metadata_anchors=metadata_anchors
    )