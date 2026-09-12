"""
Web Link Scraping & Threat Context Pipeline (link_pipeline).
Extracts grounded context from URLs, generates clean normalized Markdown (.md)
and structured metadata (.json) ready for downstream synthesis and intelligence reporting.
"""

from pipelines.link_pipeline.schema import (
    LinkMetadata,
    ExtractedLinkIOCs,
    LinkGroundingAnchor,
    LinkPipelineResult,
)
from pipelines.link_pipeline.scraper import LinkScraper
from pipelines.link_pipeline.formatter import format_link_to_markdown
from pipelines.link_pipeline.ingest import (
    LinkPipeline,
    LinkIngestionPipeline,
    ingest_link,
    process_link_pipeline,
)

__all__ = [
    "LinkPipeline",
    "LinkIngestionPipeline",
    "ingest_link",
    "process_link_pipeline",
    "LinkPipelineResult",
    "LinkMetadata",
    "ExtractedLinkIOCs",
    "LinkGroundingAnchor",
    "LinkScraper",
    "format_link_to_markdown",
]
