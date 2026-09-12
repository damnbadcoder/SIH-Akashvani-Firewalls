"""
Schema definitions for the Web Link Scraping & Intelligence Pipeline (link_pipeline).
Provides strict Pydantic contracts for web document metadata, extracted IOCs,
grounding anchors, and normalized Markdown context.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ExtractedLinkIOCs(BaseModel):
    """Deterministic cybersecurity indicators extracted from scraped web context."""
    cves: List[str] = Field(default_factory=list, description="Extracted CVE IDs (e.g., CVE-2024-38077)")
    ipv4_addresses: List[str] = Field(default_factory=list, description="Verified IPv4 addresses")
    ipv6_addresses: List[str] = Field(default_factory=list, description="Verified IPv6 addresses")
    sha256_hashes: List[str] = Field(default_factory=list, description="SHA256 hashes")
    sha1_hashes: List[str] = Field(default_factory=list, description="SHA1 hashes")
    md5_hashes: List[str] = Field(default_factory=list, description="MD5 hashes")
    domains: List[str] = Field(default_factory=list, description="Referenced domains")
    urls: List[str] = Field(default_factory=list, description="Referenced outbound or target hyperlinks")
    mitre_attack_ids: List[str] = Field(default_factory=list, description="MITRE ATT&CK technique IDs (e.g., T1059.001)")
    threat_actors: List[str] = Field(default_factory=list, description="Detected threat actor names or APTs")
    total_iocs_found: int = Field(default=0, description="Total count of all unique indicators")


class LinkGroundingAnchor(BaseModel):
    """
    Fine-grained provenance anchor attributing claims to specific web sections or text spans.
    """
    id: str = Field(..., description="Unique citation key, e.g. 'link-1', 'link-cve-2026-41822'")
    section: str = Field(default="Main Body", description="Section heading or container name")
    extracted_verbatim: str = Field(..., description="Verbatim text snippet from the web source")
    anchor_type: str = Field(default="PARAGRAPH", description="Anchor kind: HEADING, PARAGRAPH, TABLE, CODE, IOC")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction confidence score")


class LinkMetadata(BaseModel):
    """Comprehensive structural, HTTP, and semantic metadata for a scraped webpage."""
    url: str = Field(..., description="Target source URL scraped")
    canonical_url: Optional[str] = Field(default=None, description="Canonical link specified by the webpage")
    domain: str = Field(..., description="Domain name (e.g. krebsonsecurity.com)")
    title: str = Field(default="Web Document", description="Extracted webpage title")
    author: Optional[str] = Field(default=None, description="Author or byline if detected")
    description: Optional[str] = Field(default=None, description="Page summary or meta description")
    published_time: Optional[str] = Field(default=None, description="Publication timestamp if available")
    site_name: Optional[str] = Field(default=None, description="Publisher or site name (e.g. BleepingComputer)")
    status_code: int = Field(default=200, description="HTTP response status code")
    content_type: str = Field(default="text/html", description="MIME content type header")
    word_count: int = Field(default=0, description="Extracted body word count")
    character_count: int = Field(default=0, description="Extracted body character count")
    estimated_tokens: int = Field(default=0, description="Estimated token count for LLM context")
    line_count: int = Field(default=0, description="Number of text lines in extracted markdown")
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="UTC timestamp of scraping")
    sha256_checksum: str = Field(default="", description="SHA256 checksum of the normalized markdown content")
    og_metadata: Dict[str, str] = Field(default_factory=dict, description="Extracted OpenGraph properties")
    json_ld_data: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted JSON-LD structured schemas")
    response_headers: Dict[str, str] = Field(default_factory=dict, description="Relevant HTTP headers (server, date, cache-control)")


class LinkPipelineResult(BaseModel):
    """
    Unified execution result contract for the Web Link Scraping Pipeline.
    Emits clean Markdown (.md) and structured metadata (.json) payloads.
    """
    metadata: LinkMetadata = Field(..., description="Webpage metadata and HTTP telemetry")
    clean_markdown: str = Field(..., description="Normalized clean Markdown representation of the page context")
    iocs: ExtractedLinkIOCs = Field(default_factory=ExtractedLinkIOCs, description="Deterministic IOCs extracted from content")
    grounding_sources: List[LinkGroundingAnchor] = Field(default_factory=list, description="Grounding anchors and citations")
    md_file_path: Optional[str] = Field(default=None, description="Absolute or relative file path to the saved .md file")
    json_file_path: Optional[str] = Field(default=None, description="Absolute or relative file path to the saved .json file")
    execution_time_ms: int = Field(default=0, description="Total pipeline execution latency in milliseconds")
    success: bool = Field(default=True, description="Whether the scrape and context normalization succeeded")
    error_message: Optional[str] = Field(default=None, description="Error details if scraping or extraction failed")

    @property
    def anchors(self) -> List[LinkGroundingAnchor]:
        return self.grounding_sources

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
