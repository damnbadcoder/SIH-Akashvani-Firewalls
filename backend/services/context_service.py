import re
import json
from typing import Dict, Any, List, Tuple

class Enhancer1Node:
    """
    Phase 2: Enhancer-1 Node.
    Ingests the md + json context.
    Function: Connects context and groups unrelated content across heterogeneous sources.
    """

    @staticmethod
    def enhance_context(
        grounding_md: str,
        citations: List[Dict[str, Any]],
        metadata_json: Dict[str, Any],
        source_links: List[str] = None
    ) -> Tuple[str, Dict[str, Any], List[str]]:
        source_links = source_links or []
        
        # 1. Extract and cross-reference indicators across all sections
        cves = list(set(re.findall(r"\bCVE-\d{4}-\d{4,7}\b", grounding_md, re.IGNORECASE)))
        ips = list(set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", grounding_md)))
        clean_ips = [ip for ip in ips if not ip.startswith("0.") and not ip.startswith("255.") and not ip.startswith("127.")]
        
        # Identify threat actors and affected systems mentioned anywhere
        actor_match = re.search(r'["\']?([A-Z][A-Za-z0-9_\s]{2,25}(?:Collective|Group|APT\w*|Team|Bear|Panda|ShadowGate))["\']?', grounding_md)
        threat_actor = actor_match.group(1).strip() if actor_match else None

        # Group unrelated content into synthesized thematic clusters
        thematic_groups = {
            "Threat Attribution": [],
            "Exploitation & Ingress Mechanics": [],
            "Perimeter Telemetry & Indicators": [],
            "Impacted Systems & Blast Radius": [],
            "Remediation & Directives": [],
        }

        paragraphs = [p.strip() for p in grounding_md.split("\n\n") if p.strip()]
        for p in paragraphs:
            p_lower = p.lower()
            if any(k in p_lower for k in ["actor", "apt", "adversary", "campaign", "collective"]):
                thematic_groups["Threat Attribution"].append(p[:200])
            elif any(k in p_lower for k in ["exploit", "cve", "vulnerability", "deserialization", "injection", "rce"]):
                thematic_groups["Exploitation & Ingress Mechanics"].append(p[:200])
            elif any(k in p_lower for k in ["ip", "hash", "domain", "c2", "beacon", "ioc", "port"]):
                thematic_groups["Perimeter Telemetry & Indicators"].append(p[:200])
            elif any(k in p_lower for k in ["controller", "server", "switch", "ecu", "infrastructure", "affected", "blast radius"]):
                thematic_groups["Impacted Systems & Blast Radius"].append(p[:200])
            elif any(k in p_lower for k in ["mitigat", "remediat", "patch", "isolate", "quarantine", "rotate"]):
                thematic_groups["Remediation & Directives"].append(p[:200])

        # Generate enhanced key points connecting disparate inputs
        enhanced_key_points = []
        if threat_actor:
            enhanced_key_points.append(f"Attributed to adversary cluster: {threat_actor}")
        if cves:
            enhanced_key_points.append(f"Confirmed exploit vectors: {', '.join(cves)}")
        if clean_ips:
            enhanced_key_points.append(f"Active infrastructure telemetry endpoints: {', '.join(clean_ips[:4])}")
        
        for theme, items in thematic_groups.items():
            if items:
                enhanced_key_points.append(f"{theme}: Integrated {len(items)} cross-modal telemetry data points.")

        # Build enhanced metadata anchors
        enhanced_metadata = dict(metadata_json)
        enhanced_metadata["connected_context"] = {
            "threat_actor": threat_actor,
            "cves": cves,
            "perimeter_ips": clean_ips[:10],
            "thematic_coverage": {k: len(v) for k, v in thematic_groups.items() if v},
            "source_links": source_links,
            "total_citations": len(citations),
        }

        # Synthesize connection header into grounding markdown
        enhancement_banner = (
            "## 🔗 ENHANCER-1 UNIFIED CONTEXT SYNTHESIS\n"
            f"- **Threat Attribution:** {threat_actor or 'Unclassified Adversary'}\n"
            f"- **Targeted CVEs:** {', '.join(cves) if cves else 'Zero-Day / Telemetry Anomaly'}\n"
            f"- **Telemetry Ingress:** {', '.join(clean_ips[:3]) if clean_ips else 'Perimeter Gateway'}\n"
            f"- **Cross-Modal Groups:** {len([k for k, v in thematic_groups.items() if v])} active intelligence pillars\n\n"
            "---\n\n"
        )
        enhanced_md = enhancement_banner + grounding_md

        return enhanced_md, enhanced_metadata, enhanced_key_points

enhancer_1_node = Enhancer1Node()
