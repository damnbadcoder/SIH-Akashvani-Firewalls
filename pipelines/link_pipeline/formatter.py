"""
Markdown Formatter for link_pipeline.
Formats scraped web content, OpenGraph metadata, and deterministic IOCs
into a unified, publication-grade, provenance-backed Markdown artifact.
"""

from typing import List
from pipelines.link_pipeline.schema import (
    LinkMetadata,
    ExtractedLinkIOCs,
    LinkGroundingAnchor,
)


def format_link_to_markdown(
    metadata: LinkMetadata,
    body_markdown: str,
    iocs: ExtractedLinkIOCs,
    anchors: List[LinkGroundingAnchor],
) -> str:
    """
    Constructs a unified, standardized Markdown document with metadata headers,
    pre-extracted IOC blocks, and citation provenance.
    """
    lines: List[str] = []

    # 1. Document Title
    lines.append(f"# {metadata.title}\n")

    # 2. Metadata Frontmatter Block
    lines.append("| Ingestion Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Source URL** | [{metadata.url}]({metadata.url}) |")
    lines.append(f"| **Domain** | `{metadata.domain}` |")
    if metadata.site_name:
        lines.append(f"| **Publisher / Site** | {metadata.site_name} |")
    if metadata.author:
        lines.append(f"| **Author** | {metadata.author} |")
    if metadata.published_time:
        lines.append(f"| **Published Date** | `{metadata.published_time}` |")
    lines.append(f"| **Scraped At** | `{metadata.scraped_at}` |")
    lines.append(f"| **Word Count** | {metadata.word_count:,} words (~{metadata.estimated_tokens:,} tokens) |")
    lines.append(f"| **HTTP Status** | `{metadata.status_code}` ({metadata.content_type}) |")
    lines.append("")

    # 3. Meta Description / Executive Summary Callout
    if metadata.description:
        lines.append(f"> **Webpage Summary:** {metadata.description}\n")

    # 4. Deterministic Indicators of Compromise (if detected)
    if iocs.total_iocs_found > 0:
        lines.append("### Extracted Cybersecurity Indicators (Pre-LLM Grounding)")
        if iocs.cves:
            lines.append(f"- **Vulnerabilities (CVEs):** {', '.join(f'`{c}`' for c in iocs.cves)}")
        if iocs.threat_actors:
            lines.append(f"- **Identified Threat Actors:** {', '.join(f'**{a}**' for a in iocs.threat_actors)}")
        if iocs.mitre_attack_ids:
            lines.append(f"- **MITRE ATT&CK IDs:** {', '.join(f'`{m}`' for m in iocs.mitre_attack_ids)}")
        if iocs.ipv4_addresses:
            lines.append(f"- **Observed IP Addresses:** {', '.join(f'`{ip}`' for ip in iocs.ipv4_addresses[:8])}")
        if iocs.sha256_hashes:
            lines.append(f"- **SHA-256 Hashes:** {', '.join(f'`{h[:16]}...`' for h in iocs.sha256_hashes[:4])}")
        lines.append("")

    # 5. Core Article / Webpage Content
    lines.append("## Webpage Context")
    if body_markdown.strip():
        lines.append(body_markdown.strip())
    else:
        lines.append(metadata.description or "No textual body content could be extracted from this webpage.")
    lines.append("")

    # 6. Provenance & Citations Anchor Table
    if anchors:
        lines.append("### Grounding Provenance & Anchors")
        lines.append("| Citation Anchor | Section | Verbatim Evidence | Type |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for anchor in anchors[:15]:
            safe_text = anchor.extracted_verbatim.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `^{anchor.id}` | {anchor.section} | {safe_text[:90]}... | `{anchor.anchor_type}` |")
        lines.append("")

    return "\n".join(lines).strip()
