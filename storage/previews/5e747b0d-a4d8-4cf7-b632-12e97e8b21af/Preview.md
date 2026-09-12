# TECHNICAL SECURITY ADVISORY
**TRAFFIC LIGHT PROTOCOL:** TLP:AMBER+STRICT | **SEVERITY:** HIGH
**THREAT ACTOR:** Automotive Threat Landscape

---

## Executive Summary
Following CERT-In SAMVAAD 2025, CERT-In organized a specialized workshop on December 11, 2025, with 185+ participants to operationalize the Automotive Cybersecurity Guidelines & Framework across connected vehicle ecosystems [^src-1].

## Technical Analysis & Exploit Chain
Modern connected vehicles integrate complex in-vehicle networks vulnerable to spoofing, message injection, and unauthorized remote diagnostics. The framework mandates cryptographic authentication, secure boot mechanisms, and segmented gateway controllers [^src-1].

## Indicators of Compromise (IOCs)
| Type | Indicator | Context | Recommended Action |
|------|-----------|---------|-------------------|
| Network | `CAN_ID_0x000_FLOOD` | In-vehicle bus denial of service indicator | block |
| Domain | `<span style="color: red; font-weight: bold;">[SENSITIVE: telematics-sync.internal]</span>` | Internal OEM telematics staging endpoint | monitor |

## Prioritized Mitigations
1. 1. Implement Secure On-Board Communication (SecOC) for all safety-critical ECU messages [^src-1].
2. 2. Enforce strict cryptographic verification for all Over-The-Air (OTA) firmware binaries [^src-1].
3. 3. Conduct third-party audits with CERT-In empanelled auditing organizations [^src-1].

## Official Reporting
Report vehicle telematics security incidents to incident@cert-in.org.in [^src-1].