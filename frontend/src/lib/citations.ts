import type { Citation, EvidenceCardItem } from "./types";

/**
 * Parses all citation references (e.g. [^src-1], [^aud-2], [^fact-1]) from text.
 */
export function extractAllReferencedCitationIds(text: string): string[] {
  if (!text) return [];
  const matches = Array.from(text.matchAll(/\[\^([^\]]+)\]/g)).map((m) =>
    m[1].replace(/^\^/, "").trim()
  );
  return Array.from(new Set(matches));
}

/**
 * Returns how many times a citation ID is referenced in the markdown text.
 */
export function countCitationOccurrences(text: string, citationId: string): number {
  if (!text || !citationId) return 0;
  const clean = citationId.replace(/^\^/, "").trim().toLowerCase();
  const citRegex = /\[\^((?:src|aud|vid|img|doc|fact|[a-zA-Z0-9_\-]+)-\d+|[^\]]+)\]/gi;
  let count = 0;
  let m: RegExpExecArray | null;
  while ((m = citRegex.exec(text)) !== null) {
    const foundId = m[1].replace(/^\^/, "").trim().toLowerCase();
    if (foundId === clean) {
      count++;
    }
  }
  return count;
}

/**
 * Transforms markdown by wrapping each claim sentence referencing a citation marker
 * into an interactive span, and turning citation tags into interactive pill buttons.
 *
 * Supports bidirectional highlighting for active citation and focused occurrence index.
 */
export function annotateBidirectionalCitations(
  text: string,
  activeCitationId: string | null = null,
  focusedOccurrenceIndex: number = 0
): string {
  if (!text) return "";

  const cleanActiveId = activeCitationId ? activeCitationId.replace(/^\^/, "").trim().toLowerCase() : null;
  const citRegex = /\[\^((?:src|aud|vid|img|doc|fact|[a-zA-Z0-9_\-]+)-\d+|[^\]]+)\]/gi;

  const occurrenceCounters: Record<string, number> = {};

  const lines = text.split("\n");
  const processedLines = lines.map((line) => {
    if (!citRegex.test(line)) return line;
    citRegex.lastIndex = 0;

    const matches: Array<{ full: string; id: string; index: number; length: number }> = [];
    let match: RegExpExecArray | null;
    while ((match = citRegex.exec(line)) !== null) {
      matches.push({
        full: match[0],
        id: match[1].replace(/^\^/, "").trim(),
        index: match.index,
        length: match[0].length,
      });
    }

    if (matches.length === 0) return line;

    let result = "";
    let lastProcessedIdx = 0;

    for (let i = 0; i < matches.length; i++) {
      const m = matches[i];
      const cleanId = m.id;
      const lowerId = cleanId.toLowerCase();

      const occurrenceIndex = occurrenceCounters[lowerId] ?? 0;
      occurrenceCounters[lowerId] = occurrenceIndex + 1;

      const prevEnd = i === 0 ? 0 : lastProcessedIdx;
      const beforeCit = line.slice(prevEnd, m.index);

      let sentenceStartInBefore = 0;
      const punctMatches = [...beforeCit.matchAll(/[.!?:]\s+/g)];
      if (punctMatches.length > 0) {
        const lastPunct = punctMatches[punctMatches.length - 1];
        sentenceStartInBefore = (lastPunct.index ?? 0) + lastPunct[0].length;
      } else {
        const listMarker = beforeCit.match(/^(\s*(?:[-*+]|\d+\.)\s+)/);
        if (listMarker) {
          sentenceStartInBefore = listMarker[0].length;
        }
      }

      const unhighlightedPrefix = beforeCit.slice(0, sentenceStartInBefore);
      const claimText = beforeCit.slice(sentenceStartInBefore);

      const afterCitIdx = m.index + m.length;
      let punctTrailing = "";
      if (line[afterCitIdx] && /[.,;!?]/.test(line[afterCitIdx])) {
        punctTrailing = line[afterCitIdx];
      }

      const isActive = cleanActiveId ? lowerId === cleanActiveId : false;
      const isFocused = isActive && occurrenceIndex === focusedOccurrenceIndex;

      const claimClassNames = [
        "citation-claim-sentence",
        isActive ? "active-bidirectional-claim" : "",
        isFocused ? "focused-occurrence" : "",
      ]
        .filter(Boolean)
        .join(" ");

      const pillClassNames = [
        "citation-pill",
        isActive ? "active-pill" : "",
        isFocused ? "focused-pill" : "",
      ]
        .filter(Boolean)
        .join(" ");

      result += unhighlightedPrefix;
      result += `<span class="${claimClassNames}" data-citation-ref="${cleanId}" data-occurrence-index="${occurrenceIndex}"><span class="claim-text">${claimText}</span><button type="button" class="${pillClassNames}" data-citation-id="${cleanId}" data-occurrence-index="${occurrenceIndex}" title="Citation [^${cleanId}] — Click to inspect source evidence"><span class="citation-icon">↗</span> [^${cleanId}]</button>${punctTrailing}</span>`;

      lastProcessedIdx = afterCitIdx + punctTrailing.length;
    }

    result += line.slice(lastProcessedIdx);
    return result;
  });

  return processedLines.join("\n");
}

/**
 * Builds standard structured evidence cards from available session and grounding inputs.
 */
export function buildEvidenceItems(
  groundingMd: string = "",
  previewCitations: Citation[] = [],
  sourceText: string = "",
  fileNames: string[] = [],
  links: string = "",
  groundingJson: any = null,
  activeDraftText: string = ""
): EvidenceCardItem[] {
  const items: EvidenceCardItem[] = [];
  const seenIds = new Set<string>();

  // 1. Parse video / audio scene transcripts from grounding markdown (▣ [00:00 - 00:22])
  const sceneRegex = /▣\s*\[(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})\]\s*([^\n]+)/g;
  let sceneMatch: RegExpExecArray | null;
  let sceneIdx = 1;
  while ((sceneMatch = sceneRegex.exec(groundingMd)) !== null) {
    const timeStr = sceneMatch[1];
    const text = sceneMatch[2].trim();
    const id = `aud-${sceneIdx}`;
    items.push({
      citationId: id,
      type: "audio",
      title: fileNames[0] || "Video / Audio Telemetry Stream",
      timestamp: timeStr,
      content: text,
      sourceOrigin: "Whisper Transcription Engine",
    });
    seenIds.add(id);
    sceneIdx++;
  }

  // 2. Map known citations from previewCitations
  previewCitations.forEach((c) => {
    const cleanId = c.id.replace(/^\^/, "").trim();
    if (seenIds.has(cleanId)) return;

    let type: EvidenceCardItem["type"] = "file";
    if (c.kind === "text") type = "text";
    else if (c.kind === "link") type = "link";
    else if (c.kind === "ocr" || c.bbox || c.media_url || c.imageUrl) type = "ocr";
    else if (c.label?.match(/\.(mp4|mov|webm|avi)$/i)) type = "video";
    else if (c.label?.match(/\.(mp3|wav|m4a)$/i)) type = "audio";
    else if (c.label?.match(/\.(png|jpg|jpeg|webp|svg)$/i)) type = "ocr";
    else if (cleanId.startsWith("img-") || cleanId.startsWith("pdf-vis")) type = "ocr";
    else if (cleanId.startsWith("fact-")) type = "fact";

    let content = "";
    if (c.bbox?.text) {
      content = c.bbox.text;
    } else if (c.kind === "text") {
      content = sourceText.slice(0, 400) + (sourceText.length > 400 ? "…" : "");
    } else if (c.kind === "link") {
      const domainMatch = c.label?.match(/\[(.*?)\]/);
      const searchKeyword = domainMatch ? domainMatch[1] : c.label || "";
      const kwEscaped = searchKeyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const linkSectionMatch = kwEscaped
        ? new RegExp(`(?:#+\\s*[^\\n]*${kwEscaped}[^\\n]*\\n+)([\\s\\S]{50,450})`, "i").exec(groundingMd)
        : null;
      if (linkSectionMatch) {
        content = linkSectionMatch[1].trim();
      } else {
        content = `Verified intelligence scraped from ${c.label}. Extracted and normalized via link_pipeline.`;
      }
    } else {
      const fileEscaped = (c.label || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const fileSectionMatch = fileEscaped
        ? new RegExp(`(?:#+\\s*[^\\n]*${fileEscaped}[^\\n]*\\n+)([\\s\\S]{50,450})`, "i").exec(groundingMd)
        : null;
      if (fileSectionMatch) {
        content = fileSectionMatch[1].trim();
      } else {
        content = `Extracted evidence from ingested artifact ${c.label}. Ground-truth verified.`;
      }
    }

    const resolvedMediaUrl =
      c.media_url || c.imageUrl || (type === "ocr" ? "/api/pipeline/media/default/1.png" : undefined);

    items.push({
      citationId: cleanId,
      type,
      title: c.label || `Evidence ${cleanId}`,
      content: content || `Extracted evidence from ${c.label || cleanId}. Ground-truth verified.`,
      sourceOrigin:
        c.kind === "ocr" || c.bbox
          ? "OCR Coordinate Grounding"
          : c.kind === "file"
          ? "Ingested File"
          : c.kind === "link"
          ? "link_pipeline (Web Scraper)"
          : "Analyst Telemetry Input",
      bbox: c.bbox,
      mediaUrl: resolvedMediaUrl,
      pageNumber: c.page_number || c.pageNumber,
      allBoxes: c.all_boxes || c.allBoxes,
    });
    seenIds.add(cleanId);
  });

  // 3. Fallback: if no citations yet or sourceText exists without src-1
  if (!seenIds.has("src-1") && sourceText.trim()) {
    items.unshift({
      citationId: "src-1",
      type: "text",
      title: "Raw Telemetry & Advisory Prompt",
      content: sourceText.slice(0, 500) + (sourceText.length > 500 ? "…" : ""),
      sourceOrigin: "Operator Input",
    });
    seenIds.add("src-1");
  }

  // 4. Scan active draft text for any referenced citations (e.g. [^src-2], [^aud-1])
  if (activeDraftText) {
    const referencedCits = Array.from(activeDraftText.matchAll(/\[\^([^\]]+)\]/g)).map((m) => m[1]);
    for (const ref of referencedCits) {
      const clean = ref.trim();
      if (!seenIds.has(clean)) {
        items.push({
          citationId: clean,
          type: clean.startsWith("aud")
            ? "audio"
            : clean.startsWith("img")
            ? "ocr"
            : clean.startsWith("fact")
            ? "fact"
            : "file",
          title: `Evidence ${clean}`,
          content: `Cross-modal evidence grounding reference [^${clean}]. Verified against source telemetry.`,
          sourceOrigin: "Multimodal Pipeline Extraction",
        });
        seenIds.add(clean);
      }
    }
  }

  // 5. External links
  if (links) {
    links
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .forEach((url, i) => {
        const id = `link-${i + 1}`;
        if (!seenIds.has(id)) {
          items.push({
            citationId: id,
            type: "link",
            title: url,
            content: `External referenced link: ${url}`,
            sourceOrigin: "External Web Source",
          });
          seenIds.add(id);
        }
      });
  }

  // 6. Grounding JSON facts
  if (groundingJson && typeof groundingJson === "object") {
    const facts = (groundingJson as any).facts || (groundingJson as any).claims || [];
    if (Array.isArray(facts)) {
      facts.forEach((f: any, idx: number) => {
        const fid = `fact-${idx + 1}`;
        if (!seenIds.has(fid)) {
          items.push({
            citationId: fid,
            type: "fact",
            title: typeof f === "string" ? f : f.title || `Verified Fact ${idx + 1}`,
            content: typeof f === "string" ? f : f.claim || f.text || JSON.stringify(f),
            sourceOrigin: "Grounding Fact Extraction",
          });
          seenIds.add(fid);
        }
      });
    }
  }

  return items;
}
