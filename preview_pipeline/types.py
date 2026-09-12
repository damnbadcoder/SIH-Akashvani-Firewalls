import re
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum


def _coerce_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str):
        lines = [line.strip().lstrip("-*•0123456789. ") for line in v.splitlines() if line.strip()]
        return lines if lines else [v.strip()]
    return [str(v)]


def _coerce_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\b\d+\.\d+\b|\b\d+\b", v)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
    return None


def _coerce_dict_list(v: Any) -> List[Dict[str, str]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for item in v:
            if isinstance(item, dict):
                res.append({str(k): str(val) for k, val in item.items()})
            elif isinstance(item, str):
                res.append({"type": "Indicator", "indicator": item, "context": "", "action": "monitor"})
        return res
    if isinstance(v, str):
        return [{"type": "Indicator", "indicator": v, "context": "", "action": "monitor"}]
    return []


def _coerce_timeline(v: Any) -> List[Dict[str, str]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for item in v:
            if isinstance(item, dict):
                res.append({str(k): str(val) for k, val in item.items()})
            elif isinstance(item, str):
                parts = item.split("—", 1) if "—" in item else item.split("-", 1)
                if len(parts) == 2:
                    res.append({"time": parts[0].strip(), "event": parts[1].strip()})
                else:
                    res.append({"time": "00:00 UTC", "event": item.strip()})
        return res
    if isinstance(v, str):
        return [{"time": "00:00 UTC", "event": v}]
    return []


def _coerce_corrective_actions(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for item in v:
            if isinstance(item, dict):
                res.append(item)
            elif isinstance(item, str):
                res.append({"action": item, "status": "pending", "owner": "SecOps"})
        return res
    if isinstance(v, str):
        return [{"action": v, "status": "pending", "owner": "SecOps"}]
    return []


def _coerce_slides(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for item in v:
            if isinstance(item, dict):
                pts = item.get("key_points", [])
                item["key_points"] = _coerce_str_list(pts)
                res.append(item)
            elif isinstance(item, str):
                res.append({"title": item, "type": "CONTENT", "key_points": [item], "speaker_notes": ""})
        return res
    return []


def _coerce_scenes(v: Any) -> List[Dict[str, str]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for idx, item in enumerate(v, 1):
            if isinstance(item, dict):
                res.append({
                    "scene": str(item.get("scene") or item.get("title") or f"Scene {idx}"),
                    "visual": str(item.get("visual") or item.get("visual_cue") or item.get("video") or ""),
                    "narrator": str(item.get("narrator") or item.get("audio") or item.get("narration") or item.get("voiceover") or "")
                })
            elif isinstance(item, str):
                res.append({"scene": f"Scene {idx}", "visual": "", "narrator": item})
        return res
    return []


def _coerce_stages(v: Any) -> List[Dict[str, Any]]:
    if v is None:
        return []
    if isinstance(v, list):
        res = []
        for idx, item in enumerate(v, 1):
            if isinstance(item, dict):
                st = item.copy()
                st["steps"] = _coerce_str_list(st.get("steps", []))
                st["commands"] = _coerce_str_list(st.get("commands", []))
                res.append(st)
            elif isinstance(item, str):
                res.append({"stage": idx, "title": item, "steps": [item], "commands": []})
        return res
    return []


class OutputType(str, Enum):
    LINKEDIN_POST = "linkedin_post"
    SOCIAL_THREAD = "social_thread"
    ADVISORY = "advisory"
    EXEC_SUMMARY = "exec_summary"
    INCIDENT_REPORT = "incident_report"
    PRESS_RELEASE = "press_release"
    SLIDE_DECK = "slide_deck"
    VIDEO_SCRIPT = "video_script"
    PLAYBOOK = "playbook"


class SensitiveDataFlag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entity_type: str = "SENSITIVE_DATA"
    matched_text: str = ""
    char_start: int = 0
    char_end: int = 0
    severity: str = "HIGH"

    # Backward compatibility properties for legacy callers
    @property
    def match(self) -> str:
        return self.matched_text

    @property
    def type(self) -> str:
        return self.entity_type

    @property
    def location(self) -> Optional[str]:
        return f"[{self.char_start}:{self.char_end}]"


class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    marker: str = Field(description="Citation marker like [^src-1]")
    source_id: str = Field(description="Reference to source citation ID")
    description: str = Field(default="", description="What this citation supports")


# ─── Platform-Specific Structured Content ───

class LinkedInPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hook: str = Field(default="", description="Opening line - must grab attention immediately")
    threat_context: str = Field(default="", description="2-3 sentences summarizing the threat/campaign")
    key_insights: List[str] = Field(default_factory=list, description="3 bullet-point insights for engineering leaders")
    actionable_takeaways: List[str] = Field(default_factory=list, description="3 concrete actions for SecOps/IT managers")
    discussion_prompt: str = Field(default="", description="Question to drive comments engagement")
    hashtags: List[str] = Field(default_factory=list, description="3-5 relevant hashtags")
    citations_used: List[str] = Field(default_factory=list, description="Citation markers used in this preview")

    @field_validator("key_insights", "actionable_takeaways", "hashtags", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class SocialThreadPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hook_tweet: str = Field(default="", description="Tweet 1: Urgent alert + hook (<=280 chars)")
    exploit_tweet: str = Field(default="", description="Tweet 2: Exploit mechanism explained simply (<=280 chars)")
    ioc_tweet: str = Field(default="", description="Tweet 3: Key IOCs for defenders (<=280 chars)")
    mitigation_tweet: str = Field(default="", description="Tweet 4: 3 immediate defense steps (<=280 chars)")
    wrapup_tweet: str = Field(default="", description="Tweet 5: Official link + CTA + hashtags (<=280 chars)")
    all_tweets: List[str] = Field(default_factory=list, description="All tweets in order for easy rendering")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("all_tweets", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class AdvisoryPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tl_protocol: str = Field(default="TLP:AMBER+STRICT", description="Traffic Light Protocol marking")
    severity: str = Field(default="CRITICAL", description="CRITICAL / HIGH / MEDIUM")
    cvss_score: Optional[float] = Field(default=None, description="CVSS v3.1 score if available")
    cve_ids: List[str] = Field(default_factory=list, description="Associated CVE identifiers")
    threat_actor: Optional[str] = Field(default=None, description="Attributed threat actor/group")
    affected_systems: List[str] = Field(default_factory=list, description="Platforms/software versions affected")
    executive_summary: str = Field(default="", description="2-3 sentence operational summary for leadership")
    technical_analysis: str = Field(default="", description="Detailed exploit chain & MITRE ATT&CK mapping")
    iocs: List[Dict[str, str]] = Field(default_factory=list, description="List of {type, indicator, context, action}")
    mitigations: List[str] = Field(default_factory=list, description="Prioritized remediation steps")
    cert_reporting: Optional[str] = Field(default=None, description="CERT contact / reporting instructions")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("cve_ids", "affected_systems", "mitigations", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)

    @field_validator("cvss_score", mode="before")
    @classmethod
    def validate_cvss(cls, v):
        return _coerce_float(v)

    @field_validator("iocs", mode="before")
    @classmethod
    def validate_iocs(cls, v):
        return _coerce_dict_list(v)


class ExecSummaryPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bluf: str = Field(default="", description="Bottom Line Up Front - 1 sentence")
    situation: str = Field(default="", description="Operational baseline & threat context")
    complication: str = Field(default="", description="Business impact, regulatory exposure, brand risk")
    solution: str = Field(default="", description="Containment actions taken & posture hardening")
    strategic_recommendations: List[str] = Field(default_factory=list, description="Budget/tooling decisions needed")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("strategic_recommendations", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class IncidentReportPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    incident_id: str = Field(default="INC-2026-0001", description="INC-YYYY-NNNN format")
    status: str = Field(default="CONTAINED", description="CONTAINED / UNDER TRIAGE / RESOLVED")
    severity: str = Field(default="Tier 1 High", description="Tier 1 High / Tier 2 Medium / Tier 3 Low")
    timeline: List[Dict[str, str]] = Field(default_factory=list, description="[{time, event}] in UTC")
    root_cause: str = Field(default="", description="Vulnerability exploited & injection vector")
    blast_radius: List[str] = Field(default_factory=list, description="Affected hosts, services, credentials")
    corrective_actions: List[Dict[str, Any]] = Field(default_factory=list, description="[{action, status, owner}]")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("blast_radius", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)

    @field_validator("timeline", mode="before")
    @classmethod
    def validate_timeline(cls, v):
        return _coerce_timeline(v)

    @field_validator("corrective_actions", mode="before")
    @classmethod
    def validate_actions(cls, v):
        return _coerce_corrective_actions(v)


class PressReleasePreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dateline: str = Field(default="NEW DELHI — 2026", description="CITY — DATE format")
    headline: str = Field(default="", description="Clear, reassuring announcement")
    customer_impact: str = Field(default="", description="Explicit data protection confirmation")
    proactive_measures: List[str] = Field(default_factory=list, description="Engineering actions taken")
    user_guidance: List[str] = Field(default_factory=list, description="Safe practices for end-users")
    media_contact: str = Field(default="", description="PR contact details")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("proactive_measures", "user_guidance", "citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class SlideDeckPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slides: List[Dict[str, Any]] = Field(default_factory=list, description="[{title, type, key_points[], speaker_notes}]")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("slides", mode="before")
    @classmethod
    def validate_slides(cls, v):
        return _coerce_slides(v)

    @field_validator("citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class VideoScriptPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    runtime_seconds: int = Field(default=90)
    scenes: List[Dict[str, str]] = Field(default_factory=list, description="[{scene, visual, narrator}]")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("scenes", mode="before")
    @classmethod
    def validate_scenes(cls, v):
        return _coerce_scenes(v)

    @field_validator("citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


class PlaybookPreviewContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    playbook_code: str = Field(default="PB-SEC-01", description="e.g., PB-SEC-09")
    stages: List[Dict[str, Any]] = Field(default_factory=list, description="[{stage, title, steps[], commands[]}]")
    citations_used: List[str] = Field(default_factory=list)

    @field_validator("stages", mode="before")
    @classmethod
    def validate_stages(cls, v):
        return _coerce_stages(v)

    @field_validator("citations_used", mode="before")
    @classmethod
    def validate_lists(cls, v):
        return _coerce_str_list(v)


# Union of all platform-specific content
PlatformPreviewContent = Union[
    LinkedInPreviewContent,
    SocialThreadPreviewContent,
    AdvisoryPreviewContent,
    ExecSummaryPreviewContent,
    IncidentReportPreviewContent,
    PressReleasePreviewContent,
    SlideDeckPreviewContent,
    VideoScriptPreviewContent,
    PlaybookPreviewContent,
]


class PlatformPreview(BaseModel):
    model_config = ConfigDict(extra="ignore")
    platform_key: str
    display_name: str
    draft_title: str
    # Keep raw markdown for rendering/display compatibility
    draft_content: str = Field(description="Full rendered markdown for UI preview")
    # Structured content for programmatic access & final pipeline
    structured_content: Optional[PlatformPreviewContent] = None
    citations_used: List[str] = Field(default_factory=list)
    sensitive_flags: List[SensitiveDataFlag] = Field(default_factory=list)


class MultiPreviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_organization: bool
    previews: Dict[str, PlatformPreview]
    source_summary: str = ""
    # Raw extracted facts for grounding the final pipeline
    extracted_facts: List[str] = Field(default_factory=list, description="Key facts extracted from source for final deliverable grounding")
    metadata_anchors: Dict[str, Any] = Field(default_factory=dict, description="Key-value anchors from metadata JSON")