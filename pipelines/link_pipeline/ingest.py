"""
Master Web Link Ingestion & Context Extraction Pipeline (link_pipeline).
Ingests target web links, scrapes context, preserves metadata, extracts IOCs,
and generates dual-payload outputs (Normalized Markdown .md + Structured Metadata .json).
"""

import os
import re
import time
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from pipelines.base import BasePipeline
from pipelines.link_pipeline.schema import (
    LinkMetadata,
    ExtractedLinkIOCs,
    LinkGroundingAnchor,
    LinkPipelineResult,
)
from pipelines.link_pipeline.scraper import LinkScraper, estimate_tokens
from pipelines.link_pipeline.formatter import format_link_to_markdown

logger = logging.getLogger("transmute.link_pipeline")


def sanitize_filename(name: str) -> str:
    """Converts a domain or title into a safe filesystem filename."""
    cleaned = re.sub(r"[^\w\-\.]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned[:80] or "web_document"


class LinkPipeline(BasePipeline):
    """
    Unified Web Link Ingestion Pipeline.
    Satisfies BasePipeline contract and produces dual-payload .md and .json context artifacts.
    """

    def __init__(self, output_dir: str = "ingestion_outputs", timeout: float = 20.0):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scraper = LinkScraper(timeout=timeout)

    def process(
        self,
        url_input: Union[str, List[str]],
        output_dir: Optional[str] = None,
        save_outputs: bool = True,
    ) -> Union[LinkPipelineResult, List[LinkPipelineResult]]:
        """
        Polymorphic execution entry point satisfying the BasePipeline contract.
        Accepts a single URL string or a list of URLs.
        """
        if isinstance(url_input, list):
            return self.process_batch(url_input, output_dir=output_dir, save_outputs=save_outputs)
        return self.process_url(url_input, output_dir=output_dir, save_outputs=save_outputs)

    def process_url(
        self,
        url: str,
        output_dir: Optional[str] = None,
        save_outputs: bool = True,
    ) -> LinkPipelineResult:
        """
        Scrapes a single URL and generates .md and .json context outputs.
        """
        start_time = time.time()
        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            normalized_url = self.scraper.normalize_url(url)
            html_text, status_code, content_type, headers = self.scraper.fetch_url(normalized_url)

            # Parse HTML Document
            soup = BeautifulSoup(html_text, "html.parser")

            # 1. Extract Rich Structural Metadata
            metadata = self.scraper.extract_metadata(soup, normalized_url, status_code, content_type, headers)

            # 2. Strip Noise (scripts, ads, navigation, footers)
            self.scraper.clean_soup(soup)

            # 3. Locate Main Body Content
            main_container = self.scraper.find_main_content_root(soup)

            # 4. Convert DOM to Clean Markdown
            body_markdown = self.scraper.html_to_markdown(main_container, normalized_url)

            # 5. Extract Deterministic Cybersecurity Indicators
            full_raw_text = f"{metadata.title}\n{metadata.description or ''}\n{body_markdown}"
            iocs = self.scraper.extract_iocs(full_raw_text)

            # 6. Extract Provenance Anchors
            anchors = self.scraper.extract_grounding_anchors(body_markdown, iocs, metadata.domain)

            # 7. Update Metadata Statistics
            metadata.word_count = len(body_markdown.split())
            metadata.character_count = len(body_markdown)
            metadata.line_count = len(body_markdown.splitlines())
            metadata.estimated_tokens = estimate_tokens(body_markdown)

            # 8. Format Final Publication Markdown with Metadata Header & Anchors
            formatted_markdown = format_link_to_markdown(metadata, body_markdown, iocs, anchors)
            metadata.sha256_checksum = hashlib.sha256(formatted_markdown.encode("utf-8")).hexdigest()

            md_path_str: Optional[str] = None
            json_path_str: Optional[str] = None

            # 9. Save Dual-Payload Output (.md and .json files)
            if save_outputs:
                parsed_u = urlparse(normalized_url)
                path_part = parsed_u.path.strip("/").replace("/", "_")
                slug_base = f"{metadata.domain}_{path_part}" if path_part else metadata.domain
                safe_slug = sanitize_filename(slug_base)

                md_out_path = target_dir / f"{safe_slug}_context.md"
                json_out_path = target_dir / f"{safe_slug}_metadata.json"

                with open(md_out_path, "w", encoding="utf-8") as f:
                    f.write(formatted_markdown)

                md_path_str = str(md_out_path.resolve())

            exec_time = int((time.time() - start_time) * 1000)

            result = LinkPipelineResult(
                metadata=metadata,
                clean_markdown=formatted_markdown,
                iocs=iocs,
                grounding_sources=anchors,
                md_file_path=md_path_str,
                json_file_path=json_path_str,
                execution_time_ms=exec_time,
                success=True,
            )

            # Write JSON after result object is assembled to include complete serialization
            if save_outputs and md_path_str:
                json_out_path = target_dir / f"{safe_slug}_metadata.json"
                with open(json_out_path, "w", encoding="utf-8") as f:
                    json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
                result.json_file_path = str(json_out_path.resolve())

            return result

        except Exception as e:
            logger.error(f"Failed to scrape URL '{url}': {e}", exc_info=True)
            exec_time = int((time.time() - start_time) * 1000)
            domain = ""
            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = "unknown"

            fallback_metadata = LinkMetadata(
                url=url,
                domain=domain or "error",
                title=f"Failed to ingest: {url}",
                status_code=500,
                description=f"Scraping error encountered: {str(e)}",
            )
            fallback_md = f"# Error Scraping URL\n\n**Target URL:** {url}\n\n**Error:** {str(e)}"
            return LinkPipelineResult(
                metadata=fallback_metadata,
                clean_markdown=fallback_md,
                iocs=ExtractedLinkIOCs(),
                grounding_sources=[],
                execution_time_ms=exec_time,
                success=False,
                error_message=str(e),
            )

    def process_batch(
        self,
        urls: List[str],
        output_dir: Optional[str] = None,
        save_outputs: bool = True,
    ) -> List[LinkPipelineResult]:
        """Scrapes multiple URLs and aggregates their results."""
        results = []
        for url in urls:
            if url and url.strip():
                results.append(self.process_url(url.strip(), output_dir=output_dir, save_outputs=save_outputs))
        return results


# Procedural entry point matching other pipelines (ingest_text, ingest_image, ingest_audio, ingest_video)
LinkIngestionPipeline = LinkPipeline

ingest_link = lambda url, output_dir=None, save_outputs=True: LinkPipeline(
    output_dir=output_dir or "ingestion_outputs"
).process(url, output_dir=output_dir, save_outputs=save_outputs)

process_link_pipeline = ingest_link
