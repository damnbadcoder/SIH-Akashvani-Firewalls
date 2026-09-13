"""Renderers: Convert structured content to markdown for UI preview."""
from typing import Any, List


def _to_str(val: Any, joiner: str = "\n\n") -> str:
    """Coerces any value (list, dict, int, None) into a clean string representation."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (list, tuple, set)):
        items = [_to_str(x, joiner) for x in val if x is not None and str(x).strip()]
        return joiner.join(items).strip()
    if isinstance(val, dict):
        for k in ("text", "content", "summary", "description", "value", "claim"):
            if k in val and val[k]:
                return _to_str(val[k], joiner)
        return str(val)
    return str(val)


def _to_list(val: Any) -> list:
    """Coerces any value into a list."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, (tuple, set)):
        return list(val)
    if isinstance(val, str):
        lines = [line.strip().lstrip("-*•0123456789. ") for line in val.splitlines() if line.strip()]
        return lines if lines else ([val.strip()] if val.strip() else [])
    return [val]


def render_linkedin(c: dict) -> str:
    hook = _to_str(c.get("hook", ""))
    threat = _to_str(c.get("threat_context", ""), joiner=" ")
    insights = _to_list(c.get("key_insights", []))
    takeaways = _to_list(c.get("actionable_takeaways", []))
    prompt = _to_str(c.get("discussion_prompt", ""))
    hashtags = " ".join(_to_str(h) for h in _to_list(c.get("hashtags", [])))

    lines = [
        hook,
        "",
        threat,
        "",
        "## Key Insights",
    ]
    for insight in insights:
        lines.append(f"- {_to_str(insight)}")
    lines.extend([
        "",
        "## Actionable Takeaways",
    ])
    for i, takeaway in enumerate(takeaways, 1):
        lines.append(f"{i}. {_to_str(takeaway)}")
    lines.extend([
        "",
        "---",
        "",
        prompt,
        "",
        hashtags,
    ])
    return "\n".join(str(line) for line in lines)


def render_social_thread(c: dict) -> str:
    tweets = _to_list(c.get("all_tweets", []))
    if not tweets:
        tweets = [
            c.get("hook_tweet", ""),
            c.get("exploit_tweet", ""),
            c.get("ioc_tweet", ""),
            c.get("mitigation_tweet", ""),
            c.get("wrapup_tweet", ""),
        ]
    str_tweets = [_to_str(t) for t in tweets if _to_str(t)]
    return "\n---\n".join(str_tweets)


def render_advisory(c: dict) -> str:
    tlp = _to_str(c.get("tl_protocol", "TLP:AMBER+STRICT"))
    severity = _to_str(c.get("severity", "CRITICAL"))
    lines = [
        "# TECHNICAL SECURITY ADVISORY",
        f"**TRAFFIC LIGHT PROTOCOL:** {tlp} | **SEVERITY:** {severity}",
    ]
    if c.get("cvss_score"):
        lines.append(f"**CVSS v3.1:** {_to_str(c['cvss_score'])}")
    cve_ids = _to_list(c.get("cve_ids", []))
    if cve_ids:
        lines.append(f"**CVE(s):** {', '.join(_to_str(x) for x in cve_ids)}")
    if c.get("threat_actor"):
        lines.append(f"**THREAT ACTOR:** {_to_str(c['threat_actor'])}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(_to_str(c.get("executive_summary", "")))
    lines.append("")
    lines.append("## Technical Analysis & Exploit Chain")
    lines.append(_to_str(c.get("technical_analysis", "")))
    lines.append("")
    lines.append("## Indicators of Compromise (IOCs)")
    lines.append("| Type | Indicator | Context | Recommended Action |")
    lines.append("|------|-----------|---------|-------------------|")
    for ioc in _to_list(c.get("iocs", [])):
        if isinstance(ioc, dict):
            lines.append(f"| {_to_str(ioc.get('type',''))} | `{_to_str(ioc.get('indicator',''))}` | {_to_str(ioc.get('context',''))} | {_to_str(ioc.get('action',''))} |")
        else:
            lines.append(f"| Indicator | `{_to_str(ioc)}` | | monitor |")
    lines.append("")
    lines.append("## Prioritized Mitigations")
    for i, m in enumerate(_to_list(c.get("mitigations", [])), 1):
        lines.append(f"{i}. {_to_str(m)}")
    if c.get("cert_reporting"):
        lines.append("")
        lines.append("## Official Reporting")
        lines.append(_to_str(c["cert_reporting"]))
    return "\n".join(str(line) for line in lines)


def render_exec_summary(c: dict) -> str:
    lines = [
        "# EXECUTIVE BRIEF: CYBERSECURITY INCIDENT & RISK ASSESSMENT",
        "**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL",
        "",
        "---",
        "",
        "### BLUF (Bottom Line Up Front)",
        _to_str(c.get("bluf", "")),
        "",
        "### Situation",
        _to_str(c.get("situation", "")),
        "",
        "### Complication & Business Risk",
        _to_str(c.get("complication", "")),
        "",
        "### Solution & Containment Actions",
        _to_str(c.get("solution", "")),
        "",
        "### Strategic Recommendations & Decisions Required",
    ]
    for i, rec in enumerate(_to_list(c.get("strategic_recommendations", [])), 1):
        lines.append(f"{i}. {_to_str(rec)}")
    return "\n".join(str(line) for line in lines)


def render_incident_report(c: dict) -> str:
    incident_id = _to_str(c.get("incident_id", "INC-2026-XXXX"))
    status = _to_str(c.get("status", "CONTAINED"))
    severity = _to_str(c.get("severity", "Tier 1 High"))
    lines = [
        f"# INCIDENT TRIAGE & FORENSIC REPORT: {incident_id}",
        f"**Status:** {status} | **Severity:** {severity}",
        "",
        "---",
        "",
        "## Incident Timeline (UTC)",
    ]
    for entry in _to_list(c.get("timeline", [])):
        if isinstance(entry, dict):
            lines.append(f"- **{_to_str(entry.get('time', ''))}** — {_to_str(entry.get('event', ''))}")
        else:
            lines.append(f"- {_to_str(entry)}")
    lines.extend([
        "",
        "## Root Cause Analysis",
        _to_str(c.get("root_cause", "")),
        "",
        "## Blast Radius & Affected Systems",
    ])
    for item in _to_list(c.get("blast_radius", [])):
        lines.append(f"- {_to_str(item)}")
    lines.extend([
        "",
        "## Corrective Actions",
    ])
    for action in _to_list(c.get("corrective_actions", [])):
        if isinstance(action, dict):
            action_status = _to_str(action.get("status", "pending")).upper()
            action_name = _to_str(action.get("action", ""))
            owner = _to_str(action.get("owner", "TBD"))
            lines.append(f"- [{action_status}] {action_name} (Owner: {owner})")
        else:
            lines.append(f"- {_to_str(action)}")
    return "\n".join(str(line) for line in lines)


def render_press_release(c: dict) -> str:
    dateline = _to_str(c.get("dateline", "UNKNOWN — DATE"))
    headline = _to_str(c.get("headline", "Security Advisory"))
    lines = [
        "# PUBLIC SECURITY ADVISORY & STATEMENT",
        "**FOR IMMEDIATE RELEASE**",
        f"**Dateline:** {dateline}",
        "",
        "---",
        "",
        f"## {headline}",
        "",
        "### Customer Impact Statement",
        _to_str(c.get("customer_impact", "")),
        "",
        "### Proactive Protections Applied",
    ]
    proactive = c.get("proactive_measures") or c.get("remediation_steps") or []
    for m in _to_list(proactive):
        lines.append(f"- {_to_str(m)}")
    lines.extend([
        "",
        "### Safe Practices for Users",
    ])
    for g in _to_list(c.get("user_guidance", [])):
        lines.append(f"- {_to_str(g)}")
    lines.extend([
        "",
        "### Media Contact",
        _to_str(c.get("media_contact", "")),
    ])
    return "\n".join(str(line) for line in lines)


def render_slide_deck(c: dict) -> str:
    lines = ["# PRESENTATION SLIDE DECK: THREAT RESPONSE & STRATEGY", ""]
    for i, slide in enumerate(_to_list(c.get("slides", [])), 1):
        if isinstance(slide, dict):
            lines.append(f"## Slide {i}: {_to_str(slide.get('title', f'Slide {i}'))}")
            lines.append(f"**Type:** {_to_str(slide.get('type', 'CONTENT'))}")
            lines.append("")
            for point in _to_list(slide.get("key_points", [])):
                lines.append(f"- {_to_str(point)}")
            if slide.get("speaker_notes"):
                lines.append("")
                lines.append(f"*Speaker Notes:* {_to_str(slide['speaker_notes'])}")
        else:
            lines.append(f"## Slide {i}")
            lines.append(f"- {_to_str(slide)}")
        lines.append("")
    return "\n".join(str(line) for line in lines)


def render_video_script(c: dict) -> str:
    runtime = _to_str(c.get("runtime_seconds", 90))
    lines = [
        "# VIDEO NARRATION SCRIPT: CYBER THREAT BRIEFING",
        f"**Runtime:** {runtime} seconds",
        "",
        "---",
        "",
    ]
    for scene in _to_list(c.get("scenes", [])):
        if isinstance(scene, dict):
            lines.append(f"## {_to_str(scene.get('scene', 'Scene'))}")
            lines.append(f"**Visual:** {_to_str(scene.get('visual', ''))}")
            lines.append(f"**Narrator (VO):** {_to_str(scene.get('narrator', ''))}")
        else:
            lines.append(f"- {_to_str(scene)}")
        lines.append("")
    return "\n".join(str(line) for line in lines)


def render_playbook(c: dict) -> str:
    code = _to_str(c.get("playbook_code", "PB-SEC-XX"))
    lines = [
        f"# REMEDIATION PLAYBOOK: {code}",
        "**Category:** Emergency Containment & Recovery",
        "",
        "---",
        "",
    ]
    for stage in _to_list(c.get("stages", [])):
        if isinstance(stage, dict):
            lines.append(f"## Stage {_to_str(stage.get('stage', ''))}: {_to_str(stage.get('title', ''))}")
            lines.append("")
            for step in _to_list(stage.get("steps", [])):
                lines.append(f"- {_to_str(step)}")
            if stage.get("commands"):
                lines.append("")
                lines.append("**Commands:**")
                for cmd in _to_list(stage["commands"]):
                    lines.append(f"```bash\n{_to_str(cmd)}\n```")
        else:
            lines.append(f"- {_to_str(stage)}")
        lines.append("")
    return "\n".join(str(line) for line in lines)


RENDERERS = {
    "linkedin_post": render_linkedin,
    "social_thread": render_social_thread,
    "advisory": render_advisory,
    "exec_summary": render_exec_summary,
    "incident_report": render_incident_report,
    "press_release": render_press_release,
    "slide_deck": render_slide_deck,
    "video_script": render_video_script,
    "playbook": render_playbook,
}