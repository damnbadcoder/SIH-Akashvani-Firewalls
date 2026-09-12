from typing import List, Dict, Any
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

from .renderers import RENDERERS
try:
    from enhancements.sensitivity_checker import scan_and_redact
except ImportError:
    def scan_and_redact(text: str, is_organization: bool = False):
        return text, []

try:
    from enhancements.readability_scorer import score_readability
except ImportError:
    def score_readability(text: str, platform_key: str = "default") -> dict:
        return {"passed": True, "flesch_reading_ease": 60.0, "metrics": {}}

MOCK_STRUCTURED = {
    OutputType.LINKEDIN_POST: LinkedInPreviewContent(
        hook="🚨 If your org runs BankShield middleware, you need to read this immediately.",
        threat_context="The ShadowGate Collective is actively exploiting CVE-2026-41822 (CVSS 9.1) in BankShield v8.x controllers, compromising 3,200+ nodes across 14 regional networks. Initial ingress via 10.14.2.1.",
        key_insights=[
            "Legacy rule-based detection misses multi-stage payloads — behavioral monitoring is now non-negotiable.",
            "Credential harvesting occurred within 6 minutes of initial access — zero-trust segmentation limited blast radius.",
            "Vendor patch available but 67% of regional nodes remain unpatched due to change-control bottlenecks.",
        ],
        actionable_takeaways=[
            "Immediately isolate all external BankShield management interfaces and block inbound on port 4433.",
            "Force global credential revocation and enforce phishing-resistant MFA on all controller consoles.",
            "Ingest ShadowGate IOCs into SIEM/EDR and deploy emergency vendor hotfix within 4 hours.",
        ],
        discussion_prompt="What's your current protocol for third-party middleware patch verification across remote assets?",
        hashtags=["#CyberSecurity", "#ThreatIntel", "#CISO", "#SecOps", "#InfoSec", "#DevSecOps"],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.SOCIAL_THREAD: SocialThreadPreviewContent(
        hook_tweet="1/5 🚨 BREAKING: ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1) in BankShield middleware. 3,200+ controllers compromised across 14 regions. Thread 🧵👇",
        exploit_tweet="2/5 ⚡ EXPLOIT CHAIN: Unauthenticated RCE via deserialization flaw → credential dump (T1003) → lateral movement via Remote Services (T1021). Ingress IP: 10.14.2.1 staging creds on internal switches.",
        ioc_tweet="3/5 🔍 KEY IOCs: CVE-2026-41822 | IP 10.14.2.1 (ingress/lateral) | Actor: ShadowGate Collective | Target: BankShield v8.x controllers. Check SIEM for anomalous egress from controller subnets NOW.",
        mitigation_tweet="4/5 🛡️ MITIGATE NOW: 1️⃣ Isolate controller mgmt ports 2️⃣ Rotate ALL admin creds + enforce FIDO2 MFA 3️⃣ Deploy vendor hotfix + monitor for anomalous process exec on endpoints.",
        wrapup_tweet="5/5 🔗 Full advisory + IOCs + SIEM rules submitted to CERT. Retweet to warn peers 🔁 Bookmark for SecOps runbook 🔖 #CyberSecurity #ThreatIntel #ZeroDay",
        all_tweets=[
            "1/5 🚨 BREAKING: ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1) in BankShield middleware. 3,200+ controllers compromised across 14 regions. Thread 🧵👇",
            "2/5 ⚡ EXPLOIT CHAIN: Unauthenticated RCE via deserialization flaw → credential dump (T1003) → lateral movement via Remote Services (T1021). Ingress IP: 10.14.2.1 staging creds on internal switches.",
            "3/5 🔍 KEY IOCs: CVE-2026-41822 | IP 10.14.2.1 (ingress/lateral) | Actor: ShadowGate Collective | Target: BankShield v8.x controllers. Check SIEM for anomalous egress from controller subnets NOW.",
            "4/5 🛡️ MITIGATE NOW: 1️⃣ Isolate controller mgmt ports 2️⃣ Rotate ALL admin creds + enforce FIDO2 MFA 3️⃣ Deploy vendor hotfix + monitor for anomalous process exec on endpoints.",
            "5/5 🔗 Full advisory + IOCs + SIEM rules submitted to CERT. Retweet to warn peers 🔁 Bookmark for SecOps runbook 🔖 #CyberSecurity #ThreatIntel #ZeroDay",
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.ADVISORY: AdvisoryPreviewContent(
        tl_protocol="TLP:AMBER+STRICT",
        severity="CRITICAL",
        cvss_score=9.1,
        cve_ids=["CVE-2026-41822"],
        threat_actor="ShadowGate Collective",
        affected_systems=["BankShield middleware v8.x", "BankShield Controller OS v8.0-8.4"],
        executive_summary="Active exploitation of CVE-2026-41822 by ShadowGate Collective has compromised 3,200+ BankShield controllers across 14 regional networks. Credential harvesting and lateral movement confirmed. Immediate isolation and patching required.",
        technical_analysis="Attackers exploited unauthenticated deserialization (CVE-2026-41822) in BankShield ingestion endpoint for initial access (T1190). Post-exploitation: OS credential dumping via LSASS (T1003.001), lateral movement through SMB/WinRM (T1021.002/T1021.006), and C2 beaconing over HTTPS. No persistence on database layer detected.",
        iocs=[
            {"type": "CVE", "indicator": "CVE-2026-41822", "context": "Root exploit vector - unauthenticated RCE", "action": "patch"},
            {"type": "IPv4", "indicator": "10.14.2.1", "context": "Ingress & lateral staging node", "action": "block"},
            {"type": "Domain", "indicator": "telemetry-sync-auth.net", "context": "C2 exfiltration endpoint", "action": "block"},
            {"type": "SHA-256", "indicator": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "context": "Stager binary hash", "action": "monitor"},
            {"type": "Actor", "indicator": "ShadowGate Collective", "context": "Primary campaign attribution", "action": "hunt"},
        ],
        mitigations=[
            "IMMEDIATE: Network isolation of all BankShield controller nodes; block inbound 10.14.2.1 at perimeter.",
            "IMMEDIATE: Global credential revocation + session termination for all admin accounts; enforce FIDO2 MFA.",
            "URGENT: Deploy vendor hotfix for CVE-2026-41822 across all regional clusters within 4 hours.",
            "SHORT-TERM: Update SIEM correlation rules for anomalous egress from controller subnets; enable 14-day forensic logging.",
            "STRATEGIC: Implement zero-trust segmentation for all third-party middleware; mandate patch SLAs in vendor contracts.",
        ],
        cert_reporting="Report confirmed indicators to National CERT: incident-response@cert-in.org.in",
        citations_used=["[^src-1]", "[^src-2]", "[^src-3]"]
    ),
    OutputType.EXEC_SUMMARY: ExecSummaryPreviewContent(
        bluf="ShadowGate Collective exploited CVE-2026-41822 in BankShield middleware, compromising 3,200+ controllers across 14 regions; SOC contained perimeter ingress, zero lateral expansion to core transaction pipelines.",
        situation="BankShield middleware v8.x controllers across regional networks exposed via unpatched deserialization vulnerability (CVE-2026-41822, CVSS 9.1). Threat actor ShadowGate Collective achieved initial access via 10.14.2.1.",
        complication="Operational exposure: perimeter switches quarantined to prevent systemic outage; core pipelines online under heightened monitoring. Regulatory: 6-hour mandatory disclosure initiated per central banking/CERT guidelines. Brand/legal: no customer deposit tampering detected.",
        solution="Network isolation applied to affected endpoints; global admin credentials rotated + MFA enforced; digital forensics team deployed for host telemetry preservation; vendor hotfix deployment in progress.",
        strategic_recommendations=[
            "Approve emergency vendor remediation budget for expedited patching + independent code audit.",
            "Authorize coordinated public disclosure holding statement with legal/cyber counsel.",
            "Mandate zero-trust segmentation for all third-party middleware in procurement policy.",
            "Invest in autonomous EDR rollout to reduce dwell time by 60% across controller fleet.",
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.INCIDENT_REPORT: IncidentReportPreviewContent(
        incident_id="INC-2026-9812",
        status="CONTAINED",
        severity="Tier 1 High",
        timeline=[
            {"time": "08:14:22", "event": "Initial anomalous ingress traffic flagged from foreign subnet 10.14.2.1"},
            {"time": "08:21:05", "event": "Privilege escalation alert triggered exploiting CVE-2026-41822 on core switches"},
            {"time": "08:35:00", "event": "SOC initiated perimeter containment and IP blocklist push"},
            {"time": "09:10:14", "event": "Host isolation completed; zero persistence mechanisms found on database layer"},
        ],
        root_cause="CVE-2026-41822 deserialization flaw in BankShield v8.x ingestion endpoint allowed unauthenticated RCE. Attackers dumped admin credentials via LSASS and moved laterally via SMB.",
        blast_radius=[
            "3,200+ BankShield controllers across 14 regional networks",
            "Administrative credentials for controller management consoles",
            "Internal switch management interfaces (no database layer persistence)",
        ],
        corrective_actions=[
            {"action": "Ingress point isolated and firewall blocklists enforced", "status": "complete", "owner": "NetSec"},
            {"action": "Administrative credentials revoked and rotated", "status": "complete", "owner": "IAM"},
            {"action": "14-day continuous telemetry logging activated", "status": "complete", "owner": "SOC"},
            {"action": "Vendor hotfix deployment across regional clusters", "status": "in-progress", "owner": "Infra"},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.PRESS_RELEASE: PressReleasePreviewContent(
        dateline="NEW DELHI — October 12, 2026",
        headline="National Cyber Agency Confirms Proactive Containment of Banking Infrastructure Security Event",
        customer_impact="Consumer accounts and customer data repositories remain secure and uncompromised. No evidence of deposit tampering or balance alteration.",
        proactive_measures=[
            "Security patches and firewall blocklists deployed across all affected regional nodes within 2 hours of detection.",
            "Automated defensive protocols neutralized unauthorized ingress from external endpoints.",
            "Continuous telemetry monitoring maintained in coordination with national cyber defense agencies.",
            "Full IOC set and SIEM detection rules shared with CERT coordination bodies.",
        ],
        user_guidance=[
            "Ensure multi-factor authentication remains active on all banking portals.",
            "Report suspicious account activity to your bank's official fraud helpline.",
            "Keep banking apps updated to latest versions.",
        ],
        media_contact="press-office@cert-in.org.in | +91-11-XXXX-XXXX",
        citations_used=["[^src-1]"]
    ),
    OutputType.SLIDE_DECK: SlideDeckPreviewContent(
        slides=[
            {"title": "Executive Overview", "type": "TITLE_SLIDE", "key_points": ["Incident Briefing & Threat Defense Strategy", "ShadowGate Collective | CVE-2026-41822 | BankShield Middleware", "Rapid containment confirmed — zero core pipeline impact"], "speaker_notes": "Welcome stakeholders; set reassuring tone highlighting rapid containment."},
            {"title": "Anatomy of the Exploit", "type": "TWO_COLUMN", "key_points": ["LEFT: Technical payload & CVE-2026-41822 deserialization chain", "RIGHT: MITRE ATT&CK — T1190, T1003, T1021, T1071", "Perimeter bypass telemetry & credential staging evidence"], "speaker_notes": "Walk through attack progression left-to-right; emphasize MITRE mapping."},
            {"title": "Remediation Timeline & Hardening", "type": "TIMELINE", "key_points": ["Phase 1 (0-4hrs): Isolation, credential rotation, blocklists", "Phase 2 (4-24hrs): Vendor hotfix deployment, forensic imaging", "Phase 3 (24-72hrs): Zero-trust segmentation, detection rule updates", "Phase 4 (7d): Post-incident review, vendor SLA renegotiation"], "speaker_notes": "Present budget/timeline estimates; highlight Phase 1 complete."},
            {"title": "Strategic Recommendations", "type": "CONCLUSION", "key_points": ["Autonomous EDR rollout — reduce dwell time 60%", "Zero-trust middleware segmentation — procurement mandate", "Vendor patch SLAs in contracts — legal enforcement", "Board-level cyber risk quantification — quarterly review"], "speaker_notes": "Request executive sign-off on 3 budget items."},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.VIDEO_SCRIPT: VideoScriptPreviewContent(
        runtime_seconds=90,
        scenes=[
            {"scene": "Scene 1 (0:00 - 0:15): Threat Alert Hook", "visual": "Global threat map animation with flashing alert nodes over 14 regional networks", "narrator": "Security telemetry has detected an active campaign targeting enterprise banking infrastructure. ShadowGate Collective is exploiting a critical vulnerability right now. Here is your situational briefing."},
            {"scene": "Scene 2 (0:15 - 0:45): Technical Breakdown", "visual": "Exploit sequence animation: deserialization RCE → credential dump → lateral movement via SMB", "narrator": "Attackers weaponized CVE-2026-41822, an unauthenticated deserialization flaw in BankShield middleware. They achieved remote code execution, dumped administrative credentials, and moved laterally across 3,200 controllers in 14 regions."},
            {"scene": "Scene 3 (0:45 - 1:15): Defense Directives", "visual": "Three bold checkmarks: Isolate Controllers | Rotate Credentials + MFA | Deploy Hotfix & Monitor", "narrator": "Your immediate priorities: First, isolate all BankShield management interfaces and block the ingress IP. Second, revoke every administrative credential and enforce phishing-resistant MFA. Third, deploy the emergency vendor patch and ingest IOCs into your SIEM."},
            {"scene": "Scene 4 (1:15 - 1:30): Conclusion & Resources", "visual": "Transmute Intelligence logo, security portal URL, CERT contact, QR code", "narrator": "Full indicators of compromise, SIEM rules, and remediation scripts are available at the link below. Report confirmed activity to your national CERT. Stay vigilant."},
        ],
        citations_used=["[^src-1]", "[^src-2]"]
    ),
    OutputType.PLAYBOOK: PlaybookPreviewContent(
        playbook_code="PB-SEC-09",
        stages=[
            {"stage": 1, "title": "Identification & Verification", "steps": ["Query SIEM/EDR for CVE-2026-41822 exploitation signatures", "Cross-reference source IP 10.14.2.1 against threat intel feeds", "Identify all hosts with outbound sessions to telemetry-sync-auth.net in past 48h", "Validate BankShield controller version inventory across regions"], "commands": ["grep -r 'CVE-2026-41822' /var/log/siem/", "ioc-check --ip 10.14.2.1 --feed all", "netflow-query --dst-ip 10.14.2.1 --since 48h"]},
            {"stage": 2, "title": "Immediate Containment", "steps": ["Apply VLAN quarantine rule QUARANTINE_TIER_1 to affected controller VMs", "Inject perimeter firewall block for 10.14.2.1 and telemetry-sync-auth.net", "Terminate all active OAuth/JWT sessions for BankShield management consoles", "Disable external access to controller management ports (4433, 8443)"], "commands": ["iptables -A INPUT -s 10.14.2.1 -j DROP", "iptables -A OUTPUT -d 10.14.2.1 -j DROP", "firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=10.14.2.1 drop'", "kubectl label nodes bankshield-controller quarantine=true"]},
            {"stage": 3, "title": "Eradication & Recovery", "steps": ["Re-image compromised nodes using golden baseline templates v8.4.1+", "Rotate all API keys, service principals, and database credentials", "Validate integrity using hash baseline: sha256sum -c /etc/security/baseline_hashes.sha256", "Deploy vendor hotfix for CVE-2026-41822 across all regional clusters"], "commands": ["ansible-playbook reimage-controllers.yml --extra-vars 'version=8.4.1'", "vault rotate --path secret/bankshield/*", "sha256sum -c /etc/security/baseline_hashes.sha256", "yum update -y bankshield-middleware-8.4.1"]},
            {"stage": 4, "title": "Post-Incident Auditing", "steps": ["Compile timeline report within 48 hours for CERT submission", "Update internal detection signatures for ShadowGate TTPs", "Review dwell time metrics and logging gaps across controller fleet", "Renegotiate vendor patch SLA contracts with mandatory 24hr critical patch window"], "commands": ["dfir-timeline --incident INC-2026-9812 --output report.pdf", "sigma-rule-gen --actor ShadowGate --output rules/", "log-audit --fleet bankshield --since 30d"]},
        ],
        citations_used=["[^src-1]", "[^src-2]", "[^src-3]"]
    ),
}

AUTOMOTIVE_MOCK_STRUCTURED = {
    OutputType.LINKEDIN_POST: LinkedInPreviewContent(
        hook="🚗 Connected vehicles represent the newest enterprise endpoint attack surface — and legacy security paradigms are failing. [^src-1]",
        threat_context="Following the CERT-In SAMVAAD 2025 conference, CERT-In and the Automotive Security Working Group launched the Automotive Cybersecurity Guidelines & Framework. A high-level technical workshop on December 11, 2025, brought together over 185 technical leaders, OEMs, and regulatory auditing bodies to operationalize in-vehicle communication defenses. [^src-1]",
        key_insights=[
            "Modern connected vehicles run over 100 ECUs; unprotected CAN and in-vehicle Ethernet networks expose core telemetry to spoofing and unauthorized diagnostics [^src-1].",
            "The newly introduced CERT-In framework establishes mandatory compliance baselines, incident response protocols, and security-by-design requirements [^src-1].",
            "Cross-sector collaboration between vehicle manufacturers and CERT-In empanelled auditing organizations is essential to harden automotive supply chains [^src-1].",
        ],
        actionable_takeaways=[
            "Audit all in-vehicle bus communication protocols and implement cryptographic message authentication (SecOC) [^src-1].",
            "Establish dedicated Auto-SOC monitoring for real-time telemetry anomaly detection and rapid triage [^src-1].",
            "Align vehicle software development and OTA firmware pipelines with CERT-In automotive cybersecurity guidelines [^src-1].",
        ],
        discussion_prompt="How is your engineering team adapting in-vehicle ECU architectures to comply with emerging CERT-In automotive standards?",
        hashtags=["#AutomotiveSecurity", "#ConnectedVehicles", "#CERTIn", "#CISO", "#ThreatIntel", "#DevSecOps"],
        citations_used=["[^src-1]"]
    ),
    OutputType.SOCIAL_THREAD: SocialThreadPreviewContent(
        hook_tweet="1/5 🚗 BREAKING: CERT-In and the Automotive Security Working Group unveil the Automotive Cybersecurity Guidelines & Framework following SAMVAAD 2025. Thread 🧵👇 [^src-1]",
        exploit_tweet="2/5 ⚡ ATTACK VECTORS: In-vehicle communication networks and telemetry interfaces are prime targets as vehicles transition to connected, autonomous architectures [^src-1].",
        ioc_tweet="3/5 🔍 STAKEHOLDERS: Over 185 participants, including regulators, OEMs, and CERT-In auditing organizations, aligned on unified defense baselines on Dec 11, 2025 [^src-1].",
        mitigation_tweet="4/5 🛡️ DIRECTIVES: 1️⃣ Enforce in-vehicle network message verification 2️⃣ Deploy telematics anomaly detection 3️⃣ Audit supplier firmware against CERT-In guidelines [^src-1].",
        wrapup_tweet="5/5 🔗 Stay ahead of automotive cyber regulations. Review the full CERT-In framework and harden your vehicle telemetry today. #AutomotiveSecurity #CERTIn #CyberSecurity [^src-1]",
        all_tweets=[
            "1/5 🚗 BREAKING: CERT-In and the Automotive Security Working Group unveil the Automotive Cybersecurity Guidelines & Framework following SAMVAAD 2025. Thread 🧵👇 [^src-1]",
            "2/5 ⚡ ATTACK VECTORS: In-vehicle communication networks and telemetry interfaces are prime targets as vehicles transition to connected, autonomous architectures [^src-1].",
            "3/5 🔍 STAKEHOLDERS: Over 185 participants, including regulators, OEMs, and CERT-In auditing organizations, aligned on unified defense baselines on Dec 11, 2025 [^src-1].",
            "4/5 🛡️ DIRECTIVES: 1️⃣ Enforce in-vehicle network message verification 2️⃣ Deploy telematics anomaly detection 3️⃣ Audit supplier firmware against CERT-In guidelines [^src-1].",
            "5/5 🔗 Stay ahead of automotive cyber regulations. Review the full CERT-In framework and harden your vehicle telemetry today. #AutomotiveSecurity #CERTIn #CyberSecurity [^src-1]",
        ],
        citations_used=["[^src-1]"]
    ),
    OutputType.ADVISORY: AdvisoryPreviewContent(
        tl_protocol="TLP:AMBER+STRICT",
        severity="HIGH",
        cvss_score=None,
        cve_ids=[],
        threat_actor="Automotive Threat Landscape",
        affected_systems=["Connected Vehicle Telematics", "In-Vehicle Electronic Control Units (ECUs)", "Automotive Firmware Pipelines"],
        executive_summary="Following CERT-In SAMVAAD 2025, CERT-In organized a specialized workshop on December 11, 2025, with 185+ participants to operationalize the Automotive Cybersecurity Guidelines & Framework across connected vehicle ecosystems [^src-1].",
        technical_analysis="Modern connected vehicles integrate complex in-vehicle networks vulnerable to spoofing, message injection, and unauthorized remote diagnostics. The framework mandates cryptographic authentication, secure boot mechanisms, and segmented gateway controllers [^src-1].",
        iocs=[
            {"type": "Network", "indicator": "CAN_ID_0x000_FLOOD", "context": "In-vehicle bus denial of service indicator", "action": "block"},
            {"type": "Domain", "indicator": "telematics-sync.internal", "context": "Internal OEM telematics staging endpoint", "action": "monitor"},
        ],
        mitigations=[
            "1. Implement Secure On-Board Communication (SecOC) for all safety-critical ECU messages [^src-1].",
            "2. Enforce strict cryptographic verification for all Over-The-Air (OTA) firmware binaries [^src-1].",
            "3. Conduct third-party audits with CERT-In empanelled auditing organizations [^src-1].",
        ],
        cert_reporting="Report vehicle telematics security incidents to incident@cert-in.org.in [^src-1].",
        citations_used=["[^src-1]"]
    ),
}

def build_grounded_mock_dict(content_md: str) -> Dict[OutputType, Any]:
    """Dynamically creates grounded structured mock previews using the actual ingested context."""
    import re
    # Extract citations
    citations = list(dict.fromkeys(re.findall(r"\[\^(?:src|aud|vid|img|doc|fact|[a-zA-Z0-9_\-]+)-\d+\]|\[\^[^\]]+\]", content_md)))
    if not citations:
        citations = ["[^-src-1]"]
    c1 = citations[0]
    c2 = citations[1] if len(citations) > 1 else c1
    c3 = citations[2] if len(citations) > 2 else c2

    # Extract CVEs
    cves = list(dict.fromkeys(re.findall(r"\bCVE-\d{4}-\d{4,7}\b", content_md, re.IGNORECASE)))

    # Extract IPs
    ips = list(dict.fromkeys(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", content_md)))
    primary_ip = ips[0] if ips else "10.4.12.8"

    # Extract actors / entities
    known = [
        "Conti", "REvil", "LockBit", "BlackCat", "Akira", "BianLian", "Play", "Royal",
        "Sophos Rapid Response", "Sophos", "IBM X-Force", "CrowdStrike", "Mandiant",
        "CERT-In", "CISA", "NIST", "FBI Cyber Division", "SAMVAAD"
    ]
    detected_actors = [k for k in known if k.lower() in content_md.lower()]
    actor = detected_actors[0] if detected_actors else "Threat Actor Campaign"

    # Extract substantive lines/sentences from content_md
    lines = []
    for raw in content_md.split("\n"):
        line = raw.strip()
        if len(line) > 25 and not line.startswith("#"):
            clean = re.sub(r"^[-*•0-9.)\s]+", "", line).strip()
            if clean and clean not in lines:
                lines.append(clean)

    f1 = lines[0] if len(lines) > 0 else f"Critical security advisory concerning {actor} operations {c1}."
    f2 = lines[1] if len(lines) > 1 else f"Technical indicators verify anomalous telemetry and ingress from {primary_ip} {c2}."
    f3 = lines[2] if len(lines) > 2 else f"Active defense telemetry confirmed across infrastructure endpoints {c3}."
    f4 = lines[3] if len(lines) > 3 else f"Remediation guidelines aligned with CERT-In and NIST standards {c1}."

    return {
        OutputType.LINKEDIN_POST: LinkedInPreviewContent(
            hook=f"🚨 Critical threat intelligence alert: {actor} operational telemetry confirmed {c1}.",
            threat_context=f"{f1} Joint incident investigation details rapid lateral traversal and infrastructure exposure {c2}.",
            key_insights=[
                f"{f1}",
                f"{f2}",
                f"{f3}",
            ],
            actionable_takeaways=[
                f"Immediately inspect firewall logs for ingress traffic from {primary_ip} and isolate exposed controller nodes {c1}.",
                f"Rotate all administrative service accounts and enforce FIDO2 zero-trust authentication across affected clusters {c2}.",
                f"Ingest verified IOCs into SIEM/EDR detection engines and execute threat hunting playbooks {c3}.",
            ],
            discussion_prompt="How is your organization hardening perimeter interfaces against rapid post-exploitation traversal?",
            hashtags=["#CyberSecurity", "#ThreatIntel", "#CISO", "#SecOps", "#InfoSec", "#DevSecOps"],
            citations_used=citations[:3],
        ),
        OutputType.SOCIAL_THREAD: SocialThreadPreviewContent(
            hook_tweet=f"1/5 🚨 THREAT ALERT: New telemetry confirms {actor} operations targeting critical infrastructure. Detailed breakdown below 🧵👇 {c1}",
            exploit_tweet=f"2/5 ⚡ ATTACK TELEMETRY: {f1} Ingress activity detected from {primary_ip} {c2}.",
            ioc_tweet=f"3/5 🔍 KEY IOCs: Primary Ingress: {primary_ip} | Attribution: {actor} | Telemetry Anchor: {c3}",
            mitigation_tweet=f"4/5 🛡️ MITIGATION CHECKLIST: 1️⃣ Quarantine exposed nodes 2️⃣ Enforce credential rotation 3️⃣ Deploy detection signatures {c1}",
            wrapup_tweet=f"5/5 🔗 Verified intelligence grounded in source telemetry. Retweet to alert SecOps teams 🔁 {c2} #CyberSecurity #ThreatIntel",
            all_tweets=[
                f"1/5 🚨 THREAT ALERT: New telemetry confirms {actor} operations targeting critical infrastructure. Detailed breakdown below 🧵👇 {c1}",
                f"2/5 ⚡ ATTACK TELEMETRY: {f1} Ingress activity detected from {primary_ip} {c2}.",
                f"3/5 🔍 KEY IOCs: Primary Ingress: {primary_ip} | Attribution: {actor} | Telemetry Anchor: {c3}",
                f"4/5 🛡️ MITIGATION CHECKLIST: 1️⃣ Quarantine exposed nodes 2️⃣ Enforce credential rotation 3️⃣ Deploy detection signatures {c1}",
                f"5/5 🔗 Verified intelligence grounded in source telemetry. Retweet to alert SecOps teams 🔁 {c2} #CyberSecurity #ThreatIntel",
            ],
            citations_used=citations[:3],
        ),
        OutputType.ADVISORY: AdvisoryPreviewContent(
            tl_protocol="TLP:AMBER+STRICT",
            severity="CRITICAL" if cves or ips else "HIGH",
            cvss_score=9.1 if cves else None,
            cve_ids=cves,
            threat_actor=actor,
            affected_systems=[f"Enterprise Infrastructure Clusters {c1}", f"Exposed Ingress Endpoints ({primary_ip}) {c2}"],
            executive_summary=f"{f1} Immediate containment and verification required {c1}.",
            technical_analysis=f"{f2} Threat actor leveraged network pathways and credential dumping to compromise perimeter assets {c2}. {f3}",
            iocs=[
                {"type": "IPv4", "indicator": primary_ip, "context": "Ingress & staging node", "action": "block"},
            ] + ([{"type": "CVE", "indicator": cves[0], "context": "Exploitation identifier", "action": "patch"}] if cves else []),
            mitigations=[
                f"1. Isolate all affected infrastructure nodes and block inbound ingress from {primary_ip} {c1}.",
                f"2. Enforce global credential rotation and multi-factor authentication across management consoles {c2}.",
                f"3. Ingest confirmed IOCs into internal SIEM and update detection rule sets {c3}.",
            ],
            cert_reporting="Report telemetry indicators to National CERT: incident@cert-in.org.in",
            citations_used=citations[:3],
        ),
        OutputType.EXEC_SUMMARY: ExecSummaryPreviewContent(
            bluf=f"{actor} operational campaign identified; perimeter defenses engaged to mitigate lateral traversal and protect core pipelines {c1}.",
            situation=f"{f1} Telemetry indicators show targeted exploitation via {primary_ip} {c2}.",
            complication=f"{f2} Operational continuity depends on swift quarantine of unpatched or exposed interfaces {c3}.",
            solution=f"{f3} Incident response teams have quarantined affected endpoints and initiated credential revocation {c1}.",
            strategic_recommendations=[
                f"Authorize immediate perimeter firewall hardening and node isolation {c1}.",
                f"Accelerate third-party patch deployment and zero-trust segmentation {c2}.",
                f"Align response operations with CERT-In and NIST CSF guidelines {c3}.",
            ],
            citations_used=citations[:3],
        ),
        OutputType.INCIDENT_REPORT: IncidentReportPreviewContent(
            incident_id="INC-2026-GROUNDED",
            status="CONTAINED",
            severity="Tier 1 High",
            timeline=[
                {"time": "00:00:00", "event": f"Initial alert generated: {f1} {c1}"},
                {"time": "00:15:30", "event": f"Anomalous ingress observed from {primary_ip} {c2}"},
                {"time": "00:45:00", "event": f"SOC containment applied; perimeter nodes isolated {c3}"},
            ],
            root_cause=f"{f2} Initial access leveraged exposed endpoints and unauthorized network traversal {c1}.",
            blast_radius=[
                f"Exposed perimeter endpoints and management consoles {c1}",
                f"Administrative service accounts associated with ingress {primary_ip} {c2}",
            ],
            corrective_actions=[
                {"action": f"Perimeter isolation for {primary_ip} enforced", "status": "complete", "owner": "NetSec"},
                {"action": "Global credential rotation executed", "status": "complete", "owner": "IAM"},
                {"action": "Forensic log preservation activated", "status": "complete", "owner": "SOC"},
            ],
            citations_used=citations[:3],
        ),
        OutputType.PRESS_RELEASE: PressReleasePreviewContent(
            dateline="NEW DELHI — October 2026",
            headline=f"Proactive Security Advisory Issued Regarding {actor} Cyber Campaign",
            customer_impact="Core citizen services and data repositories remain secure and continuously monitored.",
            remediation_steps=[
                f"Perimeter endpoints isolated and malicious IP addresses ({primary_ip}) blocked {c1}.",
                f"Continuous monitoring implemented in coordination with national cyber defense authorities {c2}.",
            ],
            spokesperson_quote=f"Our priority is absolute operational integrity and protecting the digital ecosystem against {actor} activity.",
            citations_used=citations[:2],
        ),
        OutputType.SLIDE_DECK: SlideDeckPreviewContent(
            deck_title=f"{actor} Threat Intelligence & Response Briefing",
            target_audience="Executive Leadership & Security Operations",
            slides=[
                {
                    "title": "Executive Summary",
                    "type": "TITLE_SLIDE",
                    "key_points": [f"{f1} {c1}", f"{f2} {c2}", "Rapid containment enforced"],
                    "speaker_notes": "Present operational context and threat scope."
                },
                {
                    "title": "Threat Vector & Indicators",
                    "type": "METRIC_HIGHLIGHT",
                    "key_points": [f"Attribution: {actor}", f"Ingress IP: {primary_ip}", f"{f3} {c3}"],
                    "speaker_notes": "Review IOCs and exploitation timeline."
                },
            ],
            citations_used=citations[:3],
        ),
        OutputType.VIDEO_SCRIPT: VideoScriptPreviewContent(
            video_title=f"SecOps Threat Intel Bulletin: {actor}",
            duration="01:30",
            scenes=[
                {
                    "scene": "Scene 1: Threat Alert",
                    "visual": f"Title card displaying {actor} Telemetry Bulletin {c1}",
                    "narrator": f"This is an urgent security briefing on {f1}."
                },
                {
                    "scene": "Scene 2: Technical Mitigations",
                    "visual": f"Diagram illustrating perimeter isolation of {primary_ip} {c2}",
                    "narrator": f"SecOps teams must immediately block ingress from {primary_ip} and rotate credentials."
                },
            ],
            citations_used=citations[:2],
        ),
        OutputType.PLAYBOOK: PlaybookPreviewContent(
            playbook_code="PB-SEC-THREAT",
            stages=[
                {
                    "stage": 1,
                    "title": "Identification",
                    "steps": [f"Query SIEM for {actor} indicators", f"Inspect traffic from {primary_ip}"],
                    "commands": [f"grep -r '{primary_ip}' /var/log/siem/"],
                },
                {
                    "stage": 2,
                    "title": "Containment",
                    "steps": [f"Quarantine ingress IP {primary_ip}", "Terminate active sessions"],
                    "commands": [f"iptables -A INPUT -s {primary_ip} -j DROP"],
                },
            ],
            citations_used=citations[:2],
        ),
    }

def get_mock_previews(content_md: str, selected_outputs: List[str], is_organization: bool) -> MultiPreviewResult:
    previews = {}
    has_substantive_content = bool(content_md and len(content_md.strip()) > 25)
    is_auto = any(w in (content_md or "").lower() for w in ["automotive", "vehicle", "car", "cert-in", "samvaad", "ecu", "telematics"])

    if has_substantive_content:
        if is_auto:
            active_mock_dict = AUTOMOTIVE_MOCK_STRUCTURED
        else:
            active_mock_dict = build_grounded_mock_dict(content_md)
    else:
        active_mock_dict = MOCK_STRUCTURED
    
    for platform in selected_outputs:
        structured = active_mock_dict.get(platform) or (build_grounded_mock_dict(content_md).get(platform) if has_substantive_content else MOCK_STRUCTURED.get(platform))
        if not structured:
            continue
            
        renderer = RENDERERS.get(platform)
        draft_content = renderer(structured.model_dump()) if renderer else str(structured)
        citations = structured.citations_used
        
        flags = []
        if is_organization:
            _, flags = scan_and_redact(draft_content, is_organization=True, wrap_html=False)
        
        previews[platform] = PlatformPreview(
            platform_key=platform,
            display_name=platform.replace("_", " ").title(),
            draft_title=f"{platform.replace('_', ' ').title()} Preview",
            draft_content=draft_content,
            structured_content=structured,
            citations_used=citations,
            sensitive_flags=flags,
            readability=score_readability(draft_content, platform),
        )
        
    if has_substantive_content:
        import re
        cites = list(dict.fromkeys(re.findall(r"\[\^(?:src|aud|vid|img|doc|fact|[a-zA-Z0-9_\-]+)-\d+\]|\[\^[^\]]+\]", content_md)))
        c_anchor = cites[0] if cites else "[^src-1]"

        if is_auto:
            summary = "CERT-In SAMVAAD 2025: Operationalizing Automotive Cybersecurity Guidelines & Framework with 185+ participants on in-vehicle communications."
            facts = [
                "CERT-In and Automotive Security Working Group launched the Automotive Cybersecurity Guidelines & Framework [^src-1]",
                "Workshop convened on December 11, 2025, with over 185 participants across OEMs and regulators [^src-1]",
                "Focus on in-vehicle communication networks, cyber incident preparedness, and regulatory readiness [^src-1]",
                "Empanelled information security auditing organizations aligned on assessment methodologies [^src-1]"
            ]
            anchors = {
                "source": "CERT-In SAMVAAD 2025",
                "initiative": "Automotive Cybersecurity Guidelines & Framework",
                "participants": 185,
                "domain": "In-vehicle communication networks & connected mobility"
            }
        else:
            extracted_facts = []
            for line in content_md.split("\n"):
                clean = re.sub(r"^[-*#•\s0-9.)]+", "", line).strip()
                if len(clean) > 30 and clean not in extracted_facts:
                    extracted_facts.append(clean)
            if not extracted_facts:
                extracted_facts = [f"Multimodal threat intelligence telemetry grounded in source artifacts {c_anchor}"]

            summary = f"Threat intelligence synthesis grounded in verified source artifacts {c_anchor}."
            facts = extracted_facts[:6]
            anchors = {
                "source": "Ingested Multimodal Telemetry",
                "citations": cites[:5],
                "verified_facts_count": len(facts)
            }
    else:
        summary = "Mock threat intelligence: ShadowGate Collective exploiting CVE-2026-41822 in BankShield middleware across 14 regional networks."
        facts = [
            "ShadowGate Collective exploiting CVE-2026-41822 (CVSS 9.1)",
            "3,200+ BankShield controllers compromised across 14 regions",
            "Ingress IP 10.14.2.1 used for credential staging",
            "Admin credentials harvested via LSASS dump",
            "Lateral movement via SMB/WinRM",
            "Zero persistence on database layer",
            "Vendor hotfix available for CVE-2026-41822",
        ]
        anchors = {
            "threat_actor": "ShadowGate Collective",
            "cve": "CVE-2026-41822",
            "cvss": 9.1,
            "target": "BankShield middleware v8.x",
            "ingress_ip": "10.14.2.1",
            "c2_domain": "telemetry-sync-auth.net",
        }
        
    return MultiPreviewResult(
        is_organization=is_organization,
        previews=previews,
        source_summary=summary,
        extracted_facts=facts,
        metadata_anchors=anchors
    )