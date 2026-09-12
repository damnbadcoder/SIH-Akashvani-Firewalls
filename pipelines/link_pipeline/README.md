# 🌐 Web Link Scraping & Intelligence Pipeline (`link_pipeline`)

The **Link Pipeline** (`link_pipeline`) is an autonomous ingestion engine within the Transmute Platform. It fetches target URLs, strips boilerplate and noisy elements (scripts, advertisements, cookie banners, navigation menus), extracts OpenGraph / Twitter Cards / JSON-LD metadata, parses the core article body into clean, normalized GitHub-flavored Markdown (`.md`), extracts deterministic cybersecurity indicators (CVEs, IPs, hashes, domains, MITRE ATT&CK IDs, and threat actors), and produces structured metadata JSON (`.json`) ready for downstream LangGraph agents and deliverable synthesis.

---

## Architecture & Directory Structure

```
pipelines/link_pipeline/
├── __init__.py           # Package exports (LinkPipeline, ingest_link, schemas)
├── schema.py             # Pydantic models (LinkMetadata, ExtractedLinkIOCs, LinkPipelineResult)
├── scraper.py            # HTTP engine, noise cleaning, DOM extraction, and regex IOC parsing
├── formatter.py          # Publication-grade Markdown formatter with frontmatter & anchors
├── ingest.py             # LinkPipeline(BasePipeline) orchestrator emitting dual-payload files
├── README.md             # This documentation
└── tests/
    └── test_link_pipeline.py  # Unit tests verifying extraction, normalization & file creation
```

---

## Key Features

1. **Dual-Payload Context Artifacts:**
   - **`{domain}_{slug}_context.md`**: Standardized Markdown context featuring executive summary callout, pre-extracted IOC table, main article content, and fine-grained grounding provenance table (`[^link-...]`).
   - **`{domain}_{slug}_metadata.json`**: Complete structured JSON payload containing HTTP status code, content type, OpenGraph tags, JSON-LD structured schema, word count, character count, estimated tokens, and extracted IOCs.

2. **Pre-LLM Deterministic IOC Extraction:**
   - CVE identifiers (`CVE-YYYY-NNNN+`)
   - IPv4 / IPv6 addresses
   - File hashes (SHA-256, SHA-1, MD5)
   - MITRE ATT&CK technique IDs (`TXXXX.XXX`)
   - Known threat actors / APT groups
   - Outbound and referenced hyperlinks

3. **High-Resilience HTTP Fetching:**
   - Real browser User-Agent headers
   - Redirect following
   - SSL fallback handling
   - Structured error wrapping (never crashes parent batch jobs or server)

---

## Programmatic Usage

### Procedural Ingestion
```python
from pipelines import ingest_link

# Scrapes URL and outputs .md and .json into ingestion_outputs/
result = ingest_link("https://cert-in.org.in/advisory/sample", output_dir="ingestion_outputs")

print(result.metadata.title)
print(result.metadata.domain)
print(result.iocs.cves)
print(result.md_file_path)
print(result.json_file_path)
```

### Class-Based Ingestion
```python
from pipelines.link_pipeline import LinkPipeline

pipeline = LinkPipeline(output_dir="storage/links")
result = pipeline.process("https://example.com/cyber-threat-report")

# Access extracted markdown directly
markdown_content = result.clean_markdown

# Access structured dictionary
data_dict = result.to_dict()
```

---

## API Endpoints

- **`POST /api/pipeline/scrape-link`** (alias: `/api/link-pipeline/scrape`):
  Scrapes an individual link on demand, saves `.md` and `.json` artifacts, and optionally associates a `FileRecord` with an active session.
- **`GET /api/pipeline/download-link-artifact?path=...`**:
  Downloads generated `.md` or `.json` context artifacts securely.
- **`POST /api/generate-plan`**:
  Accepts `sourceLinks` in JSON payload or multipart form data, routing all submitted URLs through `link_pipeline`, creating database file records, and synthesizing unified previews.
