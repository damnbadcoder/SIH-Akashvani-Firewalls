"""
Web Link Scraping Engine for link_pipeline.
Fetches web content over HTTP/HTTPS, strips boilerplate, extracts OpenGraph/JSON-LD metadata,
converts the main article into clean normalized Markdown, and extracts deterministic cybersecurity IOCs.
"""

import re
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from pipelines.link_pipeline.schema import (
    LinkMetadata,
    ExtractedLinkIOCs,
    LinkGroundingAnchor,
)

logger = logging.getLogger("transmute.link_pipeline.scraper")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 TransmuteIntelBot/1.0"
)

KNOWN_THREAT_ACTORS = [
    "Lazarus Group", "Lazarus", "APT28", "Fancy Bear", "APT29", "Cozy Bear",
    "Sandworm", "APT41", "Volt Typhoon", "Salt Typhoon", "Silk Typhoon",
    "LockBit", "BlackCat", "ALPHV", "Conti", "REvil", "Akira", "Cl0p", "Clop",
    "DarkSide", "BlackMatter", "Scattered Spider", "BianLian", "Medusa",
    "Rhysida", "Dragonfly", "Turla", "Kimsuky", "MuddyWater", "FIN7",
    "ShadowGate Collective", "BankShield"
]


def estimate_tokens(text: str) -> int:
    """Approximate LLM token count (~4 characters per token)."""
    return max(1, len(text) // 4)


class LinkScraper:
    """High-resilience web scraper that extracts article text, metadata, and IOCs."""

    def __init__(self, timeout: float = 20.0, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_USER_AGENT

    def normalize_url(self, raw_url: str) -> str:
        """Ensures URL has a valid scheme and normalized format."""
        url = raw_url.strip()
        if not url:
            raise ValueError("URL cannot be empty")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL structure: {raw_url}")
        return url

    def fetch_url(self, url: str) -> Tuple[str, int, str, Dict[str, str]]:
        """
        Executes HTTP GET request with browser headers, redirect following,
        and fallback for SSL verification if self-signed certs occur.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers, verify=True) as client:
                resp = client.get(url)
                resp.encoding = resp.encoding or "utf-8"
                return resp.text, resp.status_code, resp.headers.get("content-type", "text/html"), dict(resp.headers)
        except (httpx.ConnectError, httpx.SecurityError) as ssl_err:
            logger.warning(f"SSL/Connection warning for {url}, retrying with verify=False: {ssl_err}")
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers, verify=False) as client:
                resp = client.get(url)
                resp.encoding = resp.encoding or "utf-8"
                return resp.text, resp.status_code, resp.headers.get("content-type", "text/html"), dict(resp.headers)

    def extract_metadata(self, soup: BeautifulSoup, url: str, status_code: int, content_type: str, response_headers: Dict[str, str]) -> LinkMetadata:
        """Extracts OpenGraph, Twitter Cards, JSON-LD, and HTML structural metadata."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # 1. Page Title
        title = ""
        og_title = soup.find("meta", property="og:title")
        tw_title = soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = str(og_title["content"]).strip()
        elif tw_title and tw_title.get("content"):
            title = str(tw_title["content"]).strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text().strip()

        if not title:
            title = f"Web Document - {domain}"

        # 2. Meta Description
        description = None
        og_desc = soup.find("meta", property="og:description")
        tw_desc = soup.find("meta", attrs={"name": "twitter:description"})
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            description = str(og_desc["content"]).strip()
        elif tw_desc and tw_desc.get("content"):
            description = str(tw_desc["content"]).strip()
        elif meta_desc and meta_desc.get("content"):
            description = str(meta_desc["content"]).strip()

        # 3. Author / Byline
        author = None
        meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
        if meta_author and meta_author.get("content"):
            author = str(meta_author["content"]).strip()
        else:
            byline_elem = soup.find(class_=re.compile(r"\b(?:author|byline|author-name)\b", re.I))
            if byline_elem:
                author = byline_elem.get_text().strip()

        # 4. Publication Date
        published_time = None
        pub_meta = (
            soup.find("meta", property="article:published_time")
            or soup.find("meta", attrs={"name": "publish-date"})
            or soup.find("meta", attrs={"name": "pubdate"})
            or soup.find("meta", property="og:published_time")
        )
        if pub_meta and pub_meta.get("content"):
            published_time = str(pub_meta["content"]).strip()
        else:
            time_tag = soup.find("time")
            if time_tag and time_tag.get("datetime"):
                published_time = str(time_tag["datetime"]).strip()
            elif time_tag:
                published_time = time_tag.get_text().strip()

        # 5. Site Name
        site_name = None
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            site_name = str(og_site["content"]).strip()
        else:
            site_name = domain

        # 6. Canonical URL
        canonical_url = None
        canon_tag = soup.find("link", rel="canonical")
        if canon_tag and canon_tag.get("href"):
            canonical_url = urljoin(url, str(canon_tag["href"]).strip())

        # 7. Collect all OpenGraph key-values
        og_metadata: Dict[str, str] = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property", "") or tag.get("name", "")
            if prop.startswith(("og:", "twitter:", "article:")) and tag.get("content"):
                og_metadata[prop] = str(tag["content"]).strip()

        # 8. Extract JSON-LD structured data
        json_ld_list: List[Dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw_json = script.string
                if raw_json:
                    data = json.loads(raw_json)
                    if isinstance(data, dict):
                        json_ld_list.append(data)
                        if not author and "author" in data:
                            a = data["author"]
                            if isinstance(a, dict) and "name" in a:
                                author = a["name"]
                            elif isinstance(a, list) and a and isinstance(a[0], dict):
                                author = a[0].get("name")
                        if not published_time and "datePublished" in data:
                            published_time = str(data["datePublished"])
                    elif isinstance(data, list):
                        json_ld_list.extend([d for d in data if isinstance(d, dict)])
            except Exception:
                pass

        return LinkMetadata(
            url=url,
            canonical_url=canonical_url,
            domain=domain,
            title=title,
            author=author,
            description=description,
            published_time=published_time,
            site_name=site_name,
            status_code=status_code,
            content_type=content_type,
            og_metadata=og_metadata,
            json_ld_data=json_ld_list,
            response_headers={k: v for k, v in response_headers.items() if k.lower() in ("server", "date", "content-type", "content-length", "etag")},
        )

    def clean_soup(self, soup: BeautifulSoup) -> None:
        """Removes scripts, styles, navigation bars, footers, cookie banners, and ads."""
        noise_tags = [
            "script", "style", "noscript", "svg", "canvas", "iframe",
            "header", "footer", "nav", "aside", "form", "button", "template",
            "dialog", "marquee", "applet"
        ]
        for tag in soup.find_all(noise_tags):
            tag.decompose()

        # Remove elements with typical noise class/id patterns
        noise_patterns = re.compile(
            r"\b(?:cookie-banner|ad-banner|advertisement|social-share|newsletter-signup|sidebar-widget|popup-modal|comments-section)\b",
            re.I,
        )
        for tag in soup.find_all(attrs={"class": noise_patterns}):
            # Only decompose if not a major structural element
            if tag.name not in ("body", "html", "article", "main"):
                tag.decompose()

        for tag in soup.find_all(attrs={"id": noise_patterns}):
            if tag.name not in ("body", "html", "article", "main"):
                tag.decompose()

    def find_main_content_root(self, soup: BeautifulSoup) -> Tag:
        """Identifies the primary article content container."""
        # 1. Look for semantic containers
        candidate_selectors = [
            "article",
            "main",
            "[role='main']",
            "#content",
            "#main-content",
            ".post-content",
            ".entry-content",
            ".article-body",
            ".article-content",
            ".story-body",
            ".markdown-body",
        ]
        for sel in candidate_selectors:
            container = soup.select_one(sel)
            if container and len(container.get_text(strip=True)) > 250:
                return container

        # Fallback to body or entire soup
        return soup.body or soup

    def html_to_markdown(self, element: Tag, base_url: str) -> str:
        """Converts an HTML element tree into clean, well-formatted Markdown."""
        lines: List[str] = []

        def process_node(node: Any, list_depth: int = 0) -> str:
            if isinstance(node, NavigableString):
                text = str(node)
                # Collapse internal whitespace
                return text

            if not isinstance(node, Tag):
                return ""

            tag_name = node.name.lower()

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag_name[1])
                prefix = "#" * level
                heading_text = node.get_text(strip=True)
                if heading_text:
                    return f"\n\n{prefix} {heading_text}\n\n"
                return ""

            # Paragraphs
            if tag_name == "p":
                inner = "".join(process_node(child, list_depth) for child in node.children).strip()
                if inner:
                    return f"\n\n{inner}\n\n"
                return ""

            # Code Blocks
            if tag_name == "pre":
                code_text = node.get_text()
                code_tag = node.find("code")
                lang = ""
                if code_tag and code_tag.get("class"):
                    for c in code_tag["class"]:
                        if c.startswith("language-") or c.startswith("lang-"):
                            lang = c.split("-", 1)[1]
                            break
                return f"\n\n```{lang}\n{code_text.strip()}\n```\n\n"

            if tag_name == "code":
                return f"`{node.get_text()}`"

            # Blockquotes
            if tag_name == "blockquote":
                bq_text = node.get_text(strip=True)
                if bq_text:
                    quoted = "\n".join(f"> {line}" for line in bq_text.splitlines() if line.strip())
                    return f"\n\n{quoted}\n\n"
                return ""

            # Lists
            if tag_name in ("ul", "ol"):
                items = []
                is_ordered = (tag_name == "ol")
                idx = 1
                for child in node.children:
                    if isinstance(child, Tag) and child.name == "li":
                        li_text = "".join(process_node(c, list_depth + 1) for c in child.children).strip()
                        if li_text:
                            indent = "  " * list_depth
                            bullet = f"{idx}. " if is_ordered else "- "
                            items.append(f"{indent}{bullet}{li_text}")
                            idx += 1
                if items:
                    return "\n" + "\n".join(items) + "\n"
                return ""

            # Tables
            if tag_name == "table":
                return self._table_to_markdown(node)

            # Hyperlinks
            if tag_name == "a":
                href = node.get("href", "")
                link_text = node.get_text(strip=True)
                if not link_text:
                    return ""
                if href and not href.startswith(("javascript:", "#", "mailto:", "tel:")):
                    full_url = urljoin(base_url, href)
                    return f"[{link_text}]({full_url})"
                return link_text

            # Emphasis / Strong
            if tag_name in ("b", "strong"):
                inner = node.get_text(strip=True)
                return f"**{inner}**" if inner else ""

            if tag_name in ("i", "em"):
                inner = node.get_text(strip=True)
                return f"*{inner}*" if inner else ""

            # Images
            if tag_name == "img":
                alt = node.get("alt", "Web Image")
                src = node.get("src", "")
                if src and not src.startswith("data:"):
                    full_src = urljoin(base_url, src)
                    return f"\n\n![{alt}]({full_src})\n\n"
                return ""

            # Divs, sections, spans, etc.
            inner_content = "".join(process_node(child, list_depth) for child in node.children)
            if tag_name in ("div", "section", "article"):
                return f"\n{inner_content}\n"
            return inner_content

        raw_md = process_node(element)

        # Normalize excessive blank lines (more than 2 -> 2)
        clean_md = re.sub(r"\n{3,}", "\n\n", raw_md).strip()
        return clean_md

    def _table_to_markdown(self, table_tag: Tag) -> str:
        """Converts HTML table into a Markdown table (| col | col |)."""
        rows = table_tag.find_all("tr")
        if not rows:
            return ""

        table_data = []
        for r in rows:
            cells = r.find_all(["th", "td"])
            row_vals = [re.sub(r"\s+", " ", c.get_text(strip=True)).replace("|", "\\|") for c in cells]
            if any(row_vals):
                table_data.append(row_vals)

        if not table_data:
            return ""

        # Normalize column count
        col_count = max(len(row) for row in table_data)
        normalized_data = [row + [""] * (col_count - len(row)) for row in table_data]

        header = normalized_data[0]
        divider = ["---"] * col_count

        md_lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(divider) + " |",
        ]
        for row in normalized_data[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n\n" + "\n".join(md_lines) + "\n\n"

    def extract_iocs(self, text: str) -> ExtractedLinkIOCs:
        """Deterministically extracts cybersecurity indicators from the extracted Markdown context."""
        # 1. CVEs
        cves = sorted(list(set(re.findall(r"\bCVE-\d{4}-\d{4,7}\b", text, re.IGNORECASE))))

        # 2. IPv4
        raw_ips = list(set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)))
        valid_ips = []
        for ip in raw_ips:
            parts = ip.split(".")
            if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts if p.isdigit()):
                if not (ip.startswith("0.") or ip.startswith("255.") or ip == "127.0.0.1"):
                    valid_ips.append(ip)
        valid_ips.sort()

        # 3. IPv6
        ipv6 = sorted(list(set(re.findall(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", text))))

        # 4. Hashes
        sha256 = sorted(list(set(re.findall(r"\b[a-fA-F0-9]{64}\b", text))))
        sha1 = sorted(list(set(re.findall(r"\b[a-fA-F0-9]{40}\b", text))))
        md5 = sorted(list(set(re.findall(r"\b[a-fA-F0-9]{32}\b", text))))

        # 5. MITRE ATT&CK IDs
        mitre = sorted(list(set(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text))))

        # 6. Outbound URLs & Domains
        urls = sorted(list(set(re.findall(r"https?://[^\s)\]\"'>]+", text))))
        domains = []
        for u in urls:
            try:
                p = urlparse(u)
                if p.netloc:
                    d = p.netloc.lower()
                    if d.startswith("www."):
                        d = d[4:]
                    if d not in domains:
                        domains.append(d)
            except Exception:
                pass

        # 7. Threat Actors
        actors_found = []
        for actor in KNOWN_THREAT_ACTORS:
            if re.search(rf"\b{re.escape(actor)}\b", text, re.IGNORECASE):
                if actor not in actors_found:
                    actors_found.append(actor)

        total = len(cves) + len(valid_ips) + len(sha256) + len(mitre) + len(actors_found)

        return ExtractedLinkIOCs(
            cves=cves,
            ipv4_addresses=valid_ips,
            ipv6_addresses=ipv6,
            sha256_hashes=sha256,
            sha1_hashes=sha1,
            md5_hashes=md5,
            domains=domains[:20],
            urls=urls[:30],
            mitre_attack_ids=mitre,
            threat_actors=actors_found,
            total_iocs_found=total,
        )

    def extract_grounding_anchors(self, markdown: str, iocs: ExtractedLinkIOCs, domain: str) -> List[LinkGroundingAnchor]:
        """Builds fine-grained grounding citations for key sections and claims."""
        anchors: List[LinkGroundingAnchor] = []
        lines = markdown.splitlines()

        current_section = "Web Overview"
        paragraph_idx = 1

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Heading anchor
            if line_str.startswith("#"):
                current_section = line_str.lstrip("#").strip()
                anchor_id = f"link-{domain}-h{len(anchors)+1}"
                anchors.append(
                    LinkGroundingAnchor(
                        id=anchor_id,
                        section=current_section,
                        extracted_verbatim=current_section[:120],
                        anchor_type="HEADING",
                    )
                )
            # Paragraph anchor
            elif len(line_str) > 60 and not line_str.startswith(("|", "```", ">")):
                if paragraph_idx <= 10:  # Sample prominent paragraphs
                    anchor_id = f"link-{domain}-p{paragraph_idx}"
                    anchors.append(
                        LinkGroundingAnchor(
                            id=anchor_id,
                            section=current_section,
                            extracted_verbatim=line_str[:150],
                            anchor_type="PARAGRAPH",
                        )
                    )
                    paragraph_idx += 1

        # Add specific anchors for critical IOCs
        for cve in iocs.cves[:5]:
            anchors.append(
                LinkGroundingAnchor(
                    id=f"cve-{cve.lower()}",
                    section="Vulnerability Telemetry",
                    extracted_verbatim=f"Detected CVE indicator: {cve}",
                    anchor_type="IOC",
                )
            )

        for ip in iocs.ipv4_addresses[:5]:
            anchors.append(
                LinkGroundingAnchor(
                    id=f"ip-{ip.replace('.', '-')}",
                    section="Network Telemetry",
                    extracted_verbatim=f"Observed Host / IP: {ip}",
                    anchor_type="IOC",
                )
            )

        return anchors
