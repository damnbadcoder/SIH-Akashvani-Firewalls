import type {
  Citation,
  Generation,
  GenerationParams,
  OutputTypeId,
  PlatformPreview,
  SensitiveDataFlag,
} from "./types";
import { outputTypeLabel } from "./types";

const BACKEND_URLS = [
  "", // relative URL via Vite proxy
  "http://127.0.0.1:8000",
  "http://localhost:8000",
];

async function callApi(endpoint: string, init?: RequestInit): Promise<Response> {
  const reqInit = init || { method: "GET" };
  if (endpoint.startsWith("http")) {
    return await fetch(endpoint, reqInit);
  }

  let lastError: any = null;
  for (const base of BACKEND_URLS) {
    try {
      const url = `${base}${endpoint}`;
      const res = await fetch(url, reqInit);
      if (res.status !== 502 && res.status !== 504 && res.status !== 404) {
        return res;
      }
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error("Could not connect to backend server at http://127.0.0.1:8000");
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─────────────────────────────────────────────
// Local Proofchecking Engine (Fallback & Instant)
// ─────────────────────────────────────────────

export function proofcheckSensitiveLocal(text: string): {
  auditedText: string;
  sensitiveCount: number;
  flags: SensitiveDataFlag[];
} {
  if (!text) return { auditedText: "", sensitiveCount: 0, flags: [] };

  // Protect citation markers like [^src-1]
  const citationRegex = /\[\^(?:src|aud|vid|doc|fact|[a-zA-Z0-9_\-]+)\]/gi;
  const protectedSpans: Array<{ start: number; end: number }> = [];
  let cm: RegExpExecArray | null;
  while ((cm = citationRegex.exec(text)) !== null) {
    protectedSpans.push({ start: cm.index, end: cm.index + cm[0].length });
  }

  // Protect already-redacted tokens: [REDACTED: ...], [REDACTED], [RESTRICTED]
  const redactedRegex = /\[REDACTED(?::\s*[^\]]+)?\]|\[RESTRICTED\]/gi;
  let rm: RegExpExecArray | null;
  while ((rm = redactedRegex.exec(text)) !== null) {
    protectedSpans.push({ start: rm.index, end: rm.index + rm[0].length });
  }

  // Protect classification banners: lines starting with CLASSIFICATION:, **CLASSIFICATION:**, TLP:, etc.
  const classBannerRegex = /(?:^|\n)\s*(?:\*{1,2})?(?:CLASSIFICATION|TLP|TRAFFIC LIGHT PROTOCOL|HANDLING INSTRUCTIONS?)\s*:(?:[^\n]+)/gi;
  let bm: RegExpExecArray | null;
  while ((bm = classBannerRegex.exec(text)) !== null) {
    protectedSpans.push({ start: bm.index, end: bm.index + bm[0].length });
  }

  const patterns: Array<{ regex: RegExp; type: string; severity: "CRITICAL" | "HIGH" | "MEDIUM" }> = [
    {
      regex: /\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g,
      type: "INTERNAL_IP",
      severity: "CRITICAL",
    },
    {
      regex: /\b((?:password|passwd|pwd|secret|api[_-]?key|auth[_-]?token|bearer[_-]?token|rootkit[_-]?key)\s*[:=]\s*["']?[^\s"',;]{4,}["']?)/gi,
      type: "CREDENTIAL",
      severity: "CRITICAL",
    },
    {
      regex: /(?:\\x[0-9a-fA-F]{2}){4,}|\b(?:curl|wget)\s+[^|\n]+(?:\|\s*(?:bash|sh))\b/gi,
      type: "EXPLOIT_PAYLOAD",
      severity: "CRITICAL",
    },
    {
      regex: /\b(TOP\s+SECRET(?:\s*\/\/\s*[A-Z]+)?|SECRET\s*\/\/\s*NOFORN|RESTRICTED\s+OPERATION|INTERNAL\s+ONLY(?:\s*-\s*NOT\s+FOR\s+PUBLIC)?|OPERATION\s+SHADOWGATE\s+INTERNAL)\b/gi,
      type: "CLASSIFIED_MARKING",
      severity: "HIGH",
    },
    {
      regex: /\b([a-zA-Z0-9_\-\.]+\.(?:internal|local|corp|intranet|lan)|core-db-prod-\d+|bank-hsm-\d+|dc-internal-auth)\b/gi,
      type: "INTERNAL_HOST",
      severity: "HIGH",
    },
    {
      regex: /\b([a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9-]+\.)?(?:internal|local|corp|ntro\.internal))\b|\b(EMP-[0-9]{4,8}|UID-[0-9]{4,8})\b/gi,
      type: "INTERNAL_PII",
      severity: "HIGH",
    },
  ];

  const rawFlags: Array<{
    type: string;
    matched_text: string;
    char_start: number;
    char_end: number;
    severity: "CRITICAL" | "HIGH" | "MEDIUM";
  }> = [];

  for (const p of patterns) {
    p.regex.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = p.regex.exec(text)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      const overlaps = protectedSpans.some(
        (span) => Math.max(start, span.start) < Math.min(end, span.end)
      );
      if (!overlaps) {
        rawFlags.push({
          type: p.type,
          matched_text: match[0],
          char_start: start,
          char_end: end,
          severity: p.severity,
        });
      }
    }
  }

  rawFlags.sort((a, b) => (b.char_end - b.char_start) - (a.char_end - a.char_start) || a.char_start - b.char_start);
  const selected: typeof rawFlags = [];
  for (const f of rawFlags) {
    const overlaps = selected.some(
      (s) => Math.max(f.char_start, s.char_start) < Math.min(f.char_end, s.char_end)
    );
    if (!overlaps) {
      selected.push(f);
    }
  }

  selected.sort((a, b) => a.char_start - b.char_start);

  const flags: SensitiveDataFlag[] = selected.map((f, i) => ({
    flag_id: `flag-${i + 1}`,
    entity_type: f.type,
    matched_text: f.matched_text,
    char_start: f.char_start,
    char_end: f.char_end,
    severity: f.severity,
    suggested_action: "REDACT",
  }));

  return { auditedText: text, sensitiveCount: flags.length, flags };
}

// ─────────────────────────────────────────────
// Format Blueprints (Local Synthesizer Fallback)
// ─────────────────────────────────────────────

function buildFormatBlueprint(
  id: OutputTypeId,
  sourceText: string,
  params: GenerationParams
): string {
  const snippet = sourceText.trim()
    ? sourceText.trim().slice(0, 140).replace(/\n/g, " ") + "..."
    : "Critical telemetry & perimeter threat intelligence events";

  switch (id) {
    case "advisory":
      return `# Technical Threat Advisory: TA-2026 Telemetry Bulletin
**Target Audience:** ${params.targetAudience || "SOC Analysts, CERT Teams, CISO Staff"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Section 1: Severity Banner & TLP Marking
- **TLP Status:** TLP:AMBER+STRICT | **CVSS Rating:** 9.x Critical
- One-line operational summary: "${snippet}" [^src-1].

### Section 2: Threat Overview & Timeline
- Threat actor campaign timeline and targeted subnets [^src-1].
- Chronological breakdown from initial ingress to perimeter quarantine.

### Section 3: Technical Analysis & Attack Mechanics
- Step-by-step dissection of the exploit chain and privilege escalation.
- MITRE ATT&CK technique mappings (Initial Access, Persistence, Defense Evasion).

### Section 4: Indicators of Compromise (IOCs)
- Structured indicator table: IPv4 addresses, domain endpoints, and SHA-256 hashes [^src-2].

### Section 5: Actionable Containment & Mitigations
- Prioritized remediation instructions for SOC engineers, network admins, and CERT responders.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "exec_summary":
      return `# Executive Brief: Cybersecurity Risk & Impact Assessment
**Audience:** ${params.targetAudience || "Executive Leadership & Board Members"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### 1. Situation (Operational Baseline)
- High-level operational overview & threat context ("${snippet}") [^src-1].
- Critical business operations and digital asset dependencies.

### 2. Complication (Threat Event & Exposure)
- What triggered the alert: Threat vector exploiting infrastructure perimeter.
- Quantified business risk: Potential downtime, regulatory notification obligations, and brand impact.

### 3. Solution (Containment Authorizations)
- Actions taken by the Security Operations Center to quarantine the intrusion.
- Clear, immediate sign-offs requested from executive leadership.

### 4. Strategic Recommendations & Budget Allocation
- Capital and tooling investments to harden defense posture against repeat campaigns.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "incident_report":
      return `# Incident Triage & Forensic Report
**Audience:** ${params.targetAudience || "Incident Response & Forensics Team"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Section 1: Incident Telemetry & Chronology (UTC)
- Timeline reconstruction with exact timestamps (UTC) [^src-1].
- Initial anomalous ingress and lateral movement checkpoints.

### Section 2: Root Cause & Exploitation Analysis
- Telemetry analysis based on: "${snippet}" [^src-1].
- Identification of vulnerable software version and injection vector.

### Section 3: Blast Radius & Affected Systems
- Scope of affected hosts, services, and credentials inspected by IR team.

### Section 4: Remediation & Forensic Checklist
- Immediate containment status and continuous telemetry verification audits.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "social_thread":
      return `# Social / X Thread: Threat Telemetry Breakdown
**Audience:** ${params.targetAudience || "InfoSec Community & Developers"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Tweet 1: The Urgent Hook
- 🧵 **THREAT ALERT:** Breaking intelligence on enterprise infrastructure exploit.
- Urgent threat summary & alert banner: "${snippet}" [^src-1].

### Tweet 2: Exploit Vector Analysis
- High-level breakdown of the vulnerability without jargon overload.
- Mechanism of compromise and perimeter bypass technique.

### Tweet 3: Key Indicators (IOCs)
- Key indicators security teams can check immediately (C2 IPs, stager hashes) [^src-2].

### Tweet 4: Defense Steps
- 3 actionable takeaway steps for sysadmins: isolate, patch, rotate.

### Tweet 5: Official Link & Community Wrap-up
- Official advisory link, CERT coordination, and #CyberSecurity #ThreatIntel #InfoSec.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "linkedin_post": {
      const isAuto = snippet.toLowerCase().includes("automotive") || snippet.toLowerCase().includes("cert-in") || snippet.toLowerCase().includes("vehicle");
      return `# LinkedIn Post: Threat Intelligence & Regulatory Advisory
**Audience:** ${params.targetAudience || "Tech Executives, CISOs, and SecOps Managers"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### 1. Headline Hook
- Connected and autonomous vehicles represent an expanding critical attack surface — and legacy security frameworks are insufficient [^src-1].
- Framing the strategic urgency for CISOs, vehicle architects, and infrastructure security teams.

### 2. Threat Analysis & Key Insights
- **The Threat Context:** ${isAuto ? "CERT-In SAMVAAD 2025: Unveiling of the Automotive Cybersecurity Guidelines & Framework addressing in-vehicle networks and connected mobility ecosystems." : `Operational briefing grounded in source telemetry: "${snippet}".`} [^src-1]
- **Impact Radius:** In-vehicle communication networks, ECU bus architectures, and automotive firmware supply chains.
- **Actionable Takeaways:**
  1. Audit internal vehicle network communication protocols and implement cryptographic message authentication [^src-1].
  2. Implement dedicated telematics anomaly detection aligned with national cybersecurity standards [^src-1].
  3. Engage with certified security auditing organizations to conduct comprehensive architectural risk reviews [^src-1].

### 3. Why This Matters for Leaders
- In-vehicle network isolation prevents remote lateral movement across vehicle control domains.
- Zero-trust architecture must extend from cloud backends directly to hardware edge controllers.

### 4. Discussion Prompt & Hashtags
- How is your engineering organization adapting vehicle ECU architectures to meet emerging CERT-In cybersecurity standards?
- #CyberSecurity #AutomotiveSecurity #CERTIn #CISO #ConnectedVehicles #DevSecOps

---
*Draft ready for final generation. Edit sections as needed.*`;
    }

    case "press_release":
      return `# Public Security Advisory & Press Statement
**Audience:** ${params.targetAudience || "Public, Customers & Press Media"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Section 1: Official Statement of Detection
- Clear, reassuring public announcement of detected activity and rapid intervention [^src-1].

### Section 2: Customer Impact Statement
- Explicit confirmation regarding user data protection and safety.

### Section 3: Proactive Protections Applied
- Measures taken by engineering to secure the ecosystem and collaborate with CERT authorities.

### Section 4: Safe Practices for Consumers
- Safe practices for end-users and official PR media contact details.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "slide_deck":
      return `# Slide Deck Presentation: Threat Response & Strategy
**Audience:** ${params.targetAudience || "Board of Directors & Security Committee"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Slide 1: Executive Overview (TITLE_SLIDE)
- **Title:** Incident Briefing & Threat Defense Strategy
- **Key Points:**
  - Brief summary: "${snippet}" [^src-1]
  - Immediate defensive response posture & rapid containment confirmation
- *Speaker Note:* Welcome stakeholders; set reassuring tone highlighting rapid containment.

### Slide 2: Threat Landscape & Vector Analysis (TWO_COLUMN)
- **Title:** Anatomy of the Exploit
- **Left Column:** Technical payload and CVE mapping
- **Right Column:** Perimeter bypass telemetry and MITRE ATT&CK Matrix mapping

### Slide 3: Roadmap to Zero-Trust Hardening (TIMELINE)
- **Title:** Remediation Timeline & Hardening
- 3 key phases: Isolation, Patching, and Credential Rotation

### Slide 4: Strategic Recommendations (CONCLUSION)
- **Title:** Future-Proofing Security Posture
- Tooling upgrades, budget allocation, and executive approvals needed.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "video_script":
      return `# Video Narration Script: Cyber Threat Briefing
**Audience:** ${params.targetAudience || "Threat Intelligence Viewers & Analysts"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Runtime:** 90 seconds | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Scene 1 (0:00 - 0:15): Threat Alert Hook
- **Visual:** Global threat map animation with flashing alert nodes.
- **Narrator (VO):** "Security telemetry has detected an active campaign targeting enterprise infrastructure. Here is your situational briefing."

### Scene 2 (0:15 - 0:45): Technical Breakdown
- **Visual:** Exploit sequence animation explaining: "${snippet}" [^src-1].
- **Narrator (VO):** "Attackers weaponized deserialization zero-days to achieve unauthenticated remote code execution."

### Scene 3 (0:45 - 1:15): Defense Directives
- **Visual:** 3 bold checkmarks on screen with clear actionable mitigation steps.
- **Narrator (VO):** "Your immediate priorities: block known malicious C2 IP addresses, inspect gateway authorization logs, and apply emergency patches."

### Scene 4 (1:15 - 1:30): Conclusion & Resources
- **Visual:** Transmute Intelligence logo, link to security portal, and support QR code.
- **Narrator (VO):** "For full indicators of compromise and detailed remediation scripts, visit the link below. Stay vigilant."

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    case "playbook":
      return `# Remediation Playbook: Incident Response & Containment
**Audience:** ${params.targetAudience || "Tier 2/3 SOC Engineers & Sysadmins"} (${params.audienceCategory})
**Tone:** ${params.tone} | **Detail:** ${params.detail} | **Language:** ${params.language}
**Objective:** ${params.objective}

---

### Stage 1: Identification & Verification
- Telemetry correlation against incoming indicators: "${snippet}" [^src-1].
- Cross-referencing firewall logs and egress sessions.

### Stage 2: Immediate Containment
- Network isolation commands and perimeter firewall rule injection.
- Revocation of compromised OAuth sessions and access keys.

### Stage 3: Eradication & Node Recovery
- Golden image deployment, integrity hash verification, and credential rotation.

### Stage 4: Post-Incident Auditing
- Review of dwell time, logging gaps, and automated detection rule updates.

---
*Blueprint ready for final generation. Edit sections as needed.*`;

    default:
      return `# ${outputTypeLabel(id)} Blueprint
**Audience:** ${params.targetAudience || params.audienceCategory}
**Tone:** ${params.tone} | **Language:** ${params.language}

---

### 1. Core Summary
- Operational analysis based on: "${snippet}" [^src-1].

### 2. Technical Findings & Takeaways
- Detailed indicator breakdown and defense recommendations.

---
*Blueprint ready for final generation. Edit sections as needed.*`;
  }
}

// ─────────────────────────────────────────────
// Public API Calls
// ─────────────────────────────────────────────

export async function generatePlan(
  sourceText: string,
  files: (File | string)[],
  links: string[],
  outputs: { id: OutputTypeId; params: GenerationParams }[],
  isOrganisation: boolean = false,
  email?: string,
  userId?: string,
  existingSessionId?: string
): Promise<{
  plan: string;
  previewsByType: Record<OutputTypeId, string>;
  previews: Record<string, PlatformPreview>;
  citations: Citation[];
  groundingMd?: string;
  groundingJson?: any;
  sessionId?: string;
  status?: "blueprint_ready" | "completed";
  selectedOutputs?: OutputTypeId[];
}> {
  // Attempt backend server first
  try {
    const formData = new FormData();
    formData.append("sourceText", sourceText);
    formData.append("sourceLinks", JSON.stringify(links));
    formData.append("outputs", JSON.stringify(outputs));
    formData.append("isOrganisation", String(isOrganisation));
    formData.append("userType", isOrganisation ? "Organisation" : "Normal");
    if (email) formData.append("email", email);
    if (userId) formData.append("userId", userId);
    if (existingSessionId) formData.append("sessionId", existingSessionId);

    for (const f of files) {
      if (f instanceof File) {
        formData.append("files", f);
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);

    const res = await callApi("/api/generate-plan", {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json();
      const previewsByType: Record<OutputTypeId, string> = (data.previewsByType || {}) as Record<OutputTypeId, string>;
      const previews: Record<string, PlatformPreview> = (data.previews || {}) as Record<string, PlatformPreview>;

      // Map separated previews into previewsByType if not already fully populated
      for (const [platformLabel, previewObj] of Object.entries(previews)) {
        const pObj = previewObj as PlatformPreview;
        const matchingOutput = outputs.find(
          (o) =>
            outputTypeLabel(o.id) === platformLabel ||
            o.id === pObj.output_type_id ||
            o.id === pObj.platform_key
        );
        if (matchingOutput && pObj.draft_content) {
          previewsByType[matchingOutput.id] = pObj.draft_content;
        }
      }

      const defaultPlan =
        outputs.length > 0 && previewsByType[outputs[0].id]
          ? previewsByType[outputs[0].id]
          : data.plan || "";

      return {
        plan: defaultPlan,
        previewsByType,
        previews,
        citations: data.citations || [],
        groundingMd: data.grounding_md,
        groundingJson: data.grounding_json,
        sessionId: data.sessionId || data.session_id,
        status: data.status || "blueprint_ready",
        selectedOutputs: outputs.map((o) => o.id),
      };
    } else {
      const errText = await res.text().catch(() => "");
      console.error(`[!] /api/generate-plan returned error ${res.status}:`, errText);
      throw new Error(`Backend LLM preview generation failed (${res.status}): ${errText || "Please check server logs."}`);
    }
  } catch (err: any) {
    console.error("[!] Backend server error for /api/generate-plan:", err?.message || err);
    throw new Error(`Could not generate LLM preview: ${err?.message || err}. Please verify the backend server is running with valid API keys.`);
  }

  // Graceful Local Fallback: build separated previews deterministically
  await sleep(400);

  const citations: Citation[] = [];
  let citIdx = 1;

  if (sourceText.trim()) {
    citations.push({
      id: `src-${citIdx++}`,
      label: "Raw Telemetry & Advisory Input",
      kind: "text",
    });
  }

  for (const f of files) {
    const name: string = typeof f === "string" ? f : ((f as any)?.name || String(f));
    citations.push({
      id: `src-${citIdx++}`,
      label: name,
      kind: "file",
    });
  }

  for (const l of links) {
    try {
      const url = new URL(l);
      citations.push({
        id: `src-${citIdx++}`,
        label: url.hostname + url.pathname,
        kind: "link",
      });
    } catch {
      citations.push({
        id: `src-${citIdx++}`,
        label: l,
        kind: "link",
      });
    }
  }

  const previewsByType: Record<OutputTypeId, string> = {} as Record<
    OutputTypeId,
    string
  >;
  const previews: Record<string, PlatformPreview> = {};

  for (const out of outputs) {
    let draft = buildFormatBlueprint(out.id, sourceText, out.params);
    let flaggedCount = 0;
    let flags: SensitiveDataFlag[] = [];

    // Apply pre-final proofcheck if Organisation toggle is active
    if (isOrganisation) {
      const checked = proofcheckSensitiveLocal(draft);
      draft = checked.auditedText;
      flaggedCount = checked.sensitiveCount;
      flags = checked.flags;
    }

    previewsByType[out.id] = draft;

    const label = outputTypeLabel(out.id);
    previews[label] = {
      platform_key: out.id,
      output_type_id: out.id,
      draft_title: `${label}: Operational Blueprint`,
      draft_content: draft,
      citations_used: citations.slice(0, 2).map((c) => c.id),
      sensitive_items_flagged: flaggedCount,
      sensitive_flags: flags,
    };
  }

  const defaultPlan = outputs.length > 0 ? previewsByType[outputs[0].id] : "";

  return { plan: defaultPlan, previewsByType, previews, citations };
}

export async function proofcheckPreviewDraft(
  draft: string,
  mdContent: string = "",
  jsonMetadata: any = null,
  wrapHtml: boolean = false
): Promise<{ auditedText: string; sensitiveCount: number; flags: SensitiveDataFlag[] }> {
  try {
    const res = await callApi("/api/proofcheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: draft,
        previewText: draft,
        is_organization: true,
        wrap_html: wrapHtml,
        mdContent,
        jsonMetadata,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      return {
        auditedText: wrapHtml ? data.proofcheckedText : (data.cleanText || draft),
        sensitiveCount: data.sensitiveCount,
        flags: data.flags || [],
      };
    }
  } catch {}

  return proofcheckSensitiveLocal(draft);
}

function stripElementByClass(text: string, tag: string, className: string): string {
  let lower = text.toLowerCase();
  const openPrefix = `<${tag}`;
  const classStr = className.toLowerCase();
  let startPos = 0;

  while (true) {
    const idx = lower.indexOf(openPrefix, startPos);
    if (idx === -1) break;
    const tagEnd = lower.indexOf(">", idx);
    if (tagEnd === -1) break;
    const tagHeader = lower.slice(idx, tagEnd + 1);
    if (!tagHeader.includes(classStr)) {
      startPos = idx + 1;
      continue;
    }

    let depth = 1;
    let curr = tagEnd + 1;
    const closeTag = `</${tag}>`;
    while (depth > 0 && curr < text.length) {
      if (lower.startsWith(openPrefix, curr)) {
        depth++;
        curr += openPrefix.length;
      } else if (lower.startsWith(closeTag, curr)) {
        depth--;
        if (depth === 0) break;
        curr += closeTag.length;
      } else {
        curr++;
      }
    }

    if (depth === 0) {
      const fullElement = text.slice(idx, curr + closeTag.length);
      const valMatch = fullElement.match(/class=["'][^"']*flag-matched-value[^"']*["'][^>]*>(.*?)<\/span>/i);
      let replacement = "";
      if (valMatch) {
        replacement = valMatch[1].trim();
      } else {
        const innerContent = text.slice(tagEnd + 1, curr);
        const clean = innerContent.replace(/<[^>]+>/g, "").replace(/^\[(?:⚠️|SENSITIVE)[^:]*:\s*|\s*\]$/g, "");
        replacement = clean.trim();
      }
      text = text.slice(0, idx) + replacement + text.slice(curr + closeTag.length);
      lower = text.toLowerCase();
      startPos = idx + replacement.length;
    } else {
      startPos = tagEnd + 1;
    }
  }
  return text;
}

export function stripPreviewWrappers(text: string): string {
  if (!text) return "";
  let s = text;
  // 1. Un-nest double redactions: [SENSITIVE: [REDACTED: ...]] -> [REDACTED: ...]
  s = s.replace(/\[SENSITIVE:\s*\[REDACTED(?::\s*([^\]]+))?\]\]/gi, (_m, inner) => inner ? `[REDACTED: ${inner}]` : "[REDACTED]");
  s = s.replace(/\[REDACTED:\s*\[REDACTED(?::\s*([^\]]+))?\]\]/gi, (_m, inner) => inner ? `[REDACTED: ${inner}]` : "[REDACTED]");
  s = s.replace(/\[SENSITIVE:\s*\[RESTRICTED\]\]/gi, "[RESTRICTED]");

  // 2. Strip review UI badges/spans/marks
  s = stripElementByClass(s, "span", "sensitive-flag-badge");
  s = stripElementByClass(s, "mark", "sensitive-flag-badge");
  s = s.replace(/<span\s+[^>]*style=["'][^"']*color:\s*red[^"']*["'][^>]*>(.*?)<\/span>/gis, "$1");
  s = s.replace(/<span\s+[^>]*class=["'][^"']*redacted-pill-badge[^"']*["'][^>]*>(.*?)<\/span>/gis, "$1");

  // 3. Strip standalone [SENSITIVE: ...] markers
  s = s.replace(/\[SENSITIVE:\s*\[REDACTED(?::\s*([^\]]+))?\]\]/gi, (_m, inner) => inner ? `[REDACTED: ${inner}]` : "[REDACTED]");
  s = s.replace(/\[SENSITIVE:\s*([^\]]+)\]/gi, "$1");

  // 4. Restore classification banners if accidentally touched
  s = s.replace(
    /((?:^|\n)\s*(?:\*{1,2})?(?:CLASSIFICATION|TLP|TRAFFIC LIGHT PROTOCOL)\s*:(?:\*{1,2})?\s*)(?:\[REDACTED(?::\s*[^\]]+)?\]|\[SENSITIVE:\s*([^\]]+)\])/gi,
    (_match, prefix, inner) => prefix + (inner || "")
  );

  return s;
}

export async function generateDeliverable(
  id: OutputTypeId,
  sourceText: string,
  params: GenerationParams,
  blueprint?: string,
  isOrganisation: boolean = false,
  groundingMd?: string,
  groundingJson?: any,
  sessionId?: string,
  email?: string,
  userId?: string
): Promise<string> {
  const cleanBlueprint = blueprint ? stripPreviewWrappers(blueprint) : "";
  // Attempt real backend deliverable generation
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);

    const res = await callApi("/api/generate-deliverable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        outputType: id,
        previewDraft: cleanBlueprint,
        sourceText,
        groundingMd: groundingMd || sourceText,
        groundingJson,
        params,
        isOrganisation,
        session_id: sessionId,
        sessionId,
        email,
        userId,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json();
      const content = data.final_content || data.content;
      if (content) {
        return stripPreviewWrappers(content);
      }
    } else {
      const errText = await res.text().catch(() => "");
      console.error(`[!] /api/generate-deliverable returned error ${res.status}:`, errText);
      throw new Error(`Backend deliverable generation failed (${res.status}): ${errText || "Please check server logs."}`);
    }
  } catch (err: any) {
    console.error("[!] Backend server error for /api/generate-deliverable:", err?.message || err);
    throw new Error(`Could not generate LLM deliverable: ${err?.message || err}. Please verify the backend server is running with valid API keys.`);
  }

  await sleep(600);

  const dateStr = new Date().toISOString().split("T")[0];

  // Parse telemetry and blueprint facts for realistic post generation
  const combinedText = `${blueprint || ""} ${sourceText || ""}`;
  const cleanAll = combinedText.replace(/<[^>]+>/g, "").replace(/\[\^[^\]]+\]/g, "");

  const cveMatch = cleanAll.match(/\bCVE-\d{4}-\d{4,7}\b/);
  const cve = cveMatch ? cveMatch[0] : "Identified Vulnerability";

  const ipMatch = cleanAll.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/);
  const ip = ipMatch ? ipMatch[0] : "192.168.1.100";

  const KNOWN_ACTORS = [
    "Conti", "REvil", "LockBit", "BlackCat", "ALPHV", "Lazarus", "Volt Typhoon",
    "Sophos Rapid Response", "Sophos", "IBM X-Force", "CERT-In", "NIST", "CISA"
  ];
  const matchedKnown = KNOWN_ACTORS.find((a) => cleanAll.toLowerCase().includes(a.toLowerCase()));

  const actorMatch = cleanAll.match(/['"“]([A-Z][A-Za-z0-9_\s]{3,30}(?:Collective|Group|APT\w*|Team|Bear|Panda))['"”]/) ||
                     cleanAll.match(/\b([A-Z][A-Za-z0-9_\s]{3,25}(?:Collective|Group|APT\d+))\b/);
  const actor = actorMatch ? actorMatch[1].trim() : (matchedKnown || "Identified Threat Actor");

  const sysMatch = cleanAll.match(/\b([A-Z][A-Za-z0-9]+(?:Shield|Gate|Core|Guard|Auth|Switch|OS|Server)\s*(?:middleware|platform|v\d+[\.\w]*|controller)?)\b/);
  const system = sysMatch ? sysMatch[1].trim() : "Target Infrastructure";

  const facts: string[] = [];
  if (blueprint) {
    for (const line of blueprint.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.includes("Extracted telemetry:")) {
        const fact = trimmed.split("Extracted telemetry:")[1].trim().replace(/^[-•*"' ]+|[-•*"' ]+$/g, "");
        if (fact.length > 15 && !facts.includes(fact)) facts.push(fact);
      } else if (trimmed.includes("Analysis of")) {
        const fact = trimmed.split("Analysis of")[1].trim().replace(/^[-•*"' ]+|[-•*"' ]+$/g, "");
        if (fact.length > 15 && !facts.includes(fact)) facts.push(fact);
      }
    }
  }

  if (facts.length === 0 && sourceText) {
    for (const line of sourceText.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.length > 25 && !trimmed.startsWith("#") && !facts.includes(trimmed)) {
        facts.push(trimmed);
      }
    }
  }

  const f1 = facts[0] || `Critical perimeter intrusion targeting enterprise infrastructure exploiting ${cve}.`;
  const f2 = facts[1] || `Adversary group ${actor} initiated lateral traversal via ingress endpoint ${ip}.`;
  const f3 = facts[2] || `Compromised endpoints detected across regional infrastructure controllers.`;
  const f4 = facts[3] || `Administrative credentials harvested during initial access stage.`;

  switch (id) {
    case "linkedin_post":
      return `🚨 If your organization operates enterprise infrastructure, you need to read this immediately.

A major threat intelligence development has just been confirmed:

The threat actor designated "${actor}" has actively exploited ${cve} (CVSS 9.1), targeting enterprise infrastructure. The campaign has compromised critical controllers across operational networks.

Here is what every engineering leader and CISO needs to know right now:

🔹 Entry Vector: ${f1}
🔹 Lateral Infiltration: ${f2}
🔹 Blast Radius: ${f3}
🔹 Access Risk: ${f4}

What SecOps and IT infrastructure teams should execute immediately:
1. Immediately audit and isolate all external endpoints running affected service versions.
2. Force credential revocation and zero-trust authentication across all controller management consoles.
3. Ingest confirmed threat actor indicators into your SIEM and EDR rule sets.

To security leaders and enterprise architects: What is your current protocol for third-party patch verification across remote assets?

Let's discuss actionable mitigation strategies in the comments below.

#CyberSecurity #ThreatIntel #CISO #SecOps #InfoSec #DevSecOps`;

    case "social_thread":
      return `1/5 🚨 BREAKING THREAT ALERT: Coordinated enterprise exploit detected targeting critical infrastructure.

The "${actor}" is actively exploiting ${cve} (CVSS 9.1) across widely-deployed ${system} controllers.

Here's the technical breakdown, blast radius, and immediate defense steps: 🧵👇

---

2/5 ⚠️ THE EXPLOIT CHAIN:
Threat actors achieved remote compromise via vulnerability ${cve}.

${f1} Ingress telemetry detected anomalous traffic from ${ip} targeting internal switch controllers and staging credentials.

---

3/5 🔍 BLAST RADIUS & IMPACT:
• ${f3}
• Exploit vector allows unauthorized remote takeover of controller switches.
• Active C2 beaconing and credential staging observed on internal subnets.

---

4/5 🛡️ TECHNICAL MITIGATIONS (EXECUTE NOW):
1️⃣ Isolate perimeter controller nodes and block inbound ingress on management ports.
2️⃣ Immediately revoke and rotate all administrative service credentials.
3️⃣ Deploy urgent vendor patch for ${cve} and monitor endpoint telemetry for anomalous process execution.

---

5/5 🔗 TAKEAWAYS & NEXT STEPS:
This is an active campaign targeting enterprise operational technology. Full technical indicators (IOCs) and SIEM rules have been submitted to CERT coordination.

Retweet the first tweet to warn your peers 🔁 Bookmark this thread for your SecOps runbook 🔖

#CyberSecurity #ThreatIntel #InfoSec #ZeroDay`;

    case "advisory":
      return `# TECHNICAL SECURITY ADVISORY | TA-2026-NTRO-0911
**TRAFFIC LIGHT PROTOCOL:** TLP:AMBER+STRICT | **SEVERITY:** CRITICAL (CVSS 9.1)  
**PUBLISHED BY:** Transmute Threat Intelligence & Coordination Engine  
**TARGET AUDIENCE:** SOC Analysts, CERT Responders, Network Engineers  
**EFFECTIVE DATE:** ${dateStr}  

---

## 1. Executive Threat Summary
An active, coordinated cyber intrusion campaign has been detected targeting enterprise infrastructure. The adversary group designated "${actor}" has actively exploited ${cve} (CVSS 9.1) in the ${system} platform, impacting critical controller nodes across regional networks. Immediate mitigation and containment are required.

## 2. Technical Vulnerability Analysis & Exploit Chain
- **Vulnerability Identifier:** ${cve} (CVSS v3.1 Score: 9.1 - Critical)
- **Target Platform:** ${system} (v8.x and related deployment clusters)
- **Exploitation Vector:** Remote Code Execution via unauthenticated input handling.
- **Lateral Movement:** ${f2}
- **MITRE ATT&CK Mapping:**
  - Initial Access: Exploit Public-Facing Application (T1190)
  - Credential Access: OS Credential Dumping (T1003)
  - Lateral Movement: Remote Services (T1021)

## 3. Indicators of Compromise (IOC) Matrix
| Indicator Type | Observable | Context / Association | Recommended Action |
| :--- | :--- | :--- | :--- |
| Vulnerability | ${cve} | Root Exploit Vector | Emergency Hotfix |
| IPv4 Address | ${ip} | Ingress & Lateral Staging Node | Immediate Perimeter Block |
| Threat Actor | ${actor} | Primary Campaign Attribution | Deep SIEM Threat Hunt |
| Target Asset | ${system} | Vulnerable Service | Quarantine & Upgrade |

## 4. Prioritized Remediation & Defense Steps
1. **Immediate Network Isolation:** Segment and isolate all controller nodes running ${system} until integrity is validated.
2. **Credential Invalidation:** Force global password resets and session termination for all administrative accounts.
3. **Firmware & Patch Deployment:** Apply vendor hotfix for ${cve} across all regional clusters.
4. **Log Retention & SIEM Ingestion:** Update SIEM correlation rules to flag anomalous egress from internal controller subnets.

## 5. Official Reporting & CERT Signoff
Report confirmed indicators and telemetry anomalies to the National CERT Incident Hotline: \`incident-response@cert-in.org.in\`.`;

    case "exec_summary":
      return `# MEMORANDUM FOR THE BOARD OF DIRECTORS & EXECUTIVE LEADERSHIP
**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL  
**DATE:** ${dateStr}  
**SUBJECT:** Executive Risk Assessment — Threat Intelligence Incident TA-2026  

---

### 1. Bottom Line Up Front (BLUF)
A sophisticated intrusion campaign designated "${actor}" has targeted core digital infrastructure, exploiting vulnerability ${cve} in ${system}. The attack has exposed regional controller nodes and network switches. The Security Operations Center has contained perimeter ingress and zeroed immediate lateral expansion.

### 2. Quantified Business & Regulatory Exposure
- **Operational Availability:** Perimeter switches were quarantined to prevent systemic outage; core transaction pipelines remain online under heightened telemetry monitoring.
- **Regulatory Reporting Obligations:** Mandatory 6-hour incident disclosure initiated in accordance with central banking and national CERT guidelines.
- **Brand & Legal Exposure:** No evidence of customer deposit tampering or account balance alteration detected to date.

### 3. Immediate Containment Actions Executed
- Network isolation applied to affected controller endpoints.
- Global administrative credentials rotated and multi-factor authentication enforced across management consoles.
- Digital forensics team deployed to preserve host telemetry and disk images for audit compliance.

### 4. Decisions & Authorizations Required from Executive Leadership
1. **Emergency Vendor Remediation Budget:** Authorization for expedited vendor patching and independent third-party code audit.
2. **Regulatory & Communications Alignment:** Approval of coordinated public disclosure holding statement.
3. **Legal Counsel Engagement:** Formal briefing of external cybersecurity legal counsel.`;

    case "incident_report":
      return `# Incident Triage & Forensic Report: INC-2026-9812
**Investigation Lead:** DFIR Command Team | **Status:** CONTAINED / UNDER TRIAGE  
**Severity:** Tier 1 High | **Date:** ${dateStr}  

---

## 1. Incident Timeline (UTC)
- **08:14:22** — Initial anomalous ingress traffic flagged from foreign subnet ${ip}.
- **08:21:05** — Privilege escalation alert triggered exploiting ${cve} on core switches.
- **08:35:00** — SOC initiated perimeter containment and IP blocklist push.
- **09:10:14** — Host isolation completed; zero persistence mechanisms found on database layer.

## 2. Root Cause Analysis
The attack exploited ${cve} within the ${system} platform. Attackers leveraged deserialization flaws to achieve remote privilege escalation and dump administrative credentials.

## 3. Compromised Assets & Blast Radius
- ${f3}
- Forensic host validation confirms ingress attempts via ${ip}.

## 4. Corrective Actions Completed
- [x] Ingress point isolated and firewall blocklists enforced.
- [x] Administrative credentials revoked and rotated.
- [x] 14-day continuous telemetry logging activated.`;

    case "press_release":
      return `# PUBLIC SECURITY ADVISORY & STATEMENT
**FOR IMMEDIATE RELEASE**  
**Dateline:** NEW DELHI — ${dateStr}  
**Media Contact:** press-office@cert-in.org.in  

---

### Statement on Proactive Containment of Infrastructure Security Event

National cybersecurity coordination authorities today issued an update regarding proactive defensive measures deployed across regional digital infrastructure.

Security operations centers identified anomalous activity targeting ${system} controllers associated with vulnerability ${cve}. Automated defensive protocols were initiated immediately, neutralizing unauthorized ingress from external endpoints.

**Key Facts for the Public and Partners:**
- **Customer Protection:** Consumer accounts and customer data repositories remain secure and uncompromised.
- **Proactive Protections:** Security patches and firewall blocklists have been deployed across all affected regional nodes.
- **Ongoing Coordination:** Continuous telemetry monitoring is actively maintained in coordination with national cyber defense agencies.

We remain committed to complete operational transparency and safeguarding the integrity of the national digital ecosystem.`;

    default:
      return `# ${outputTypeLabel(id)}: Intelligence Deliverable
**Published Date:** ${dateStr} | **Status:** Verified  

---

### Operational Intelligence Summary
An active security event was detected targeting ${system} infrastructure through vulnerability ${cve}. Automated defense rules have quarantined ingress endpoints from ${ip}.

**Key Findings:**
- ${f1}
- ${f2}
- ${f3}

**Next Steps:**
Ensure all administrative accounts undergo credential rotation and apply the vendor patch immediately.`;
  }
}

export async function regenerateDeliverable(
  id: OutputTypeId,
  sourceText: string,
  params: GenerationParams,
  refinement: string
): Promise<string> {
  const base = await generateDeliverable(id, sourceText, params);
  return `${base}\n\n---\n*Updated with refinement directive: "${refinement}"*`;
}

export async function autosavePreviewDraft(
  sessionId: string,
  outputType: string,
  editedContent: string
): Promise<boolean> {
  if (!sessionId) return false;
  try {
    const res = await callApi(`/api/previews/${sessionId}/autosave`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_type: outputType,
        edited_content: editedContent,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchUserHistory(email?: string, userId?: string): Promise<Generation[]> {
  try {
    const query = email ? `email=${encodeURIComponent(email)}` : userId ? `user_id=${encodeURIComponent(userId)}` : "";
    const res = await callApi(`/api/history${query ? `?${query}` : ""}`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        return data as Generation[];
      }
    }
  } catch (err) {
    console.warn("Failed to fetch user history from backend:", err);
  }
  return [];
}
