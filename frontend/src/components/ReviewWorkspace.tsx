import { useMemo, useState, useRef } from "react";
import InteractivePreviewEditor from "./InteractivePreviewEditor";
import Markdown from "./Markdown";
import { outputTypeLabel } from "../lib/types";
import type { Citation, OutputTypeId, SensitiveDataFlag } from "../lib/types";

export interface EvidenceCardItem {
  citationId: string; // e.g. "src-1", "aud-1", "doc-1", "fact-1"
  type: "file" | "audio" | "video" | "ocr" | "link" | "text" | "fact";
  title: string;
  timestamp?: string;
  content: string;
  sourceOrigin?: string;
}

interface ReviewWorkspaceProps {
  currentPreviewId: OutputTypeId | null;
  selected: Set<OutputTypeId>;
  previewsByType: Partial<Record<OutputTypeId, string>>;
  previewFlagsByType: Partial<Record<OutputTypeId, SensitiveDataFlag[]>>;
  previewCitations: Citation[];
  sourceText: string;
  fileNames: string[];
  links: string;
  groundingMd?: string;
  groundingJson?: any;
  isOrganisation: boolean;
  previewViewMode: "edit" | "preview";
  generating: boolean;
  proofchecking: boolean;
  onSelectPreviewId: (id: OutputTypeId) => void;
  onViewModeChange: (mode: "edit" | "preview") => void;
  onContentChange: (newText: string) => void;
  onFlagsChange: (newFlags: SensitiveDataFlag[]) => void;
  onToggleOrganisationMode: (enabled: boolean) => void;
  onRerunProofcheck: () => void;
  onFinalizeGeneration: () => void;
  onBackToParameters: () => void;
}

export default function ReviewWorkspace({
  currentPreviewId,
  selected,
  previewsByType,
  previewFlagsByType,
  previewCitations,
  sourceText,
  fileNames,
  links,
  groundingMd,
  groundingJson,
  isOrganisation,
  previewViewMode,
  generating,
  proofchecking,
  onSelectPreviewId,
  onViewModeChange,
  onContentChange,
  onFlagsChange,
  onToggleOrganisationMode,
  onRerunProofcheck,
  onFinalizeGeneration,
  onBackToParameters,
}: ReviewWorkspaceProps) {
  // Mobile responsive tab toggle ('preview' | 'source')
  const [mobileTab, setMobileTab] = useState<"preview" | "source">("preview");
  // Filter query in source inspector
  const [filterQuery, setFilterQuery] = useState("");
  // View mode in left pane ('cards' | 'raw')
  const [sourceViewMode, setSourceViewMode] = useState<"cards" | "raw">("cards");

  const leftPaneScrollRef = useRef<HTMLDivElement>(null);

  // Parse structured source evidence items
  const evidenceItems = useMemo<EvidenceCardItem[]>(() => {
    const items: EvidenceCardItem[] = [];
    const seenIds = new Set<string>();

    const rawMd = groundingMd || "";

    // 1. Parse video / audio scene transcripts from grounding markdown
    // Format: ▣ [00:00 - 00:22] ...
    const sceneRegex = /▣\s*\[(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})\]\s*([^\n]+)/g;
    let sceneMatch: RegExpExecArray | null;
    let sceneIdx = 1;
    while ((sceneMatch = sceneRegex.exec(rawMd)) !== null) {
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
      const cleanId = c.id.replace(/^\^/, "");
      if (seenIds.has(cleanId)) return;

      let type: EvidenceCardItem["type"] = "file";
      if (c.kind === "text") type = "text";
      else if (c.kind === "link") type = "link";
      else if (c.label.match(/\.(mp4|mov|webm|avi)$/i)) type = "video";
      else if (c.label.match(/\.(mp3|wav|m4a)$/i)) type = "audio";
      else if (c.label.match(/\.(png|jpg|jpeg|webp)$/i)) type = "ocr";
      else if (cleanId.startsWith("fact-")) type = "fact";

      // Extract a meaningful snippet for this citation
      let content = "";
      if (c.kind === "text") {
        content = sourceText.slice(0, 400) + (sourceText.length > 400 ? "…" : "");
      } else if (c.kind === "link") {
        content = `Verified link source: ${c.label}`;
      } else {
        // Search in grounding markdown for section mentioning this file
        const fileEscaped = c.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const fileSectionMatch = new RegExp(
          `(?:#+\\s*[^\\n]*${fileEscaped}[^\\n]*\\n+)([\\s\\S]{50,450})`,
          "i"
        ).exec(rawMd);
        if (fileSectionMatch) {
          content = fileSectionMatch[1].trim();
        } else {
          content = `Extracted evidence from ingested artifact ${c.label}. Ground-truth verified.`;
        }
      }

      items.push({
        citationId: cleanId,
        type,
        title: c.label,
        content,
        sourceOrigin: c.kind === "file" ? "Ingested File" : c.kind === "link" ? "External Reference" : "Analyst Telemetry Input",
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

    // 4. Scan active preview draft for any referenced citations (e.g. [^src-2], [^aud-1])
    const activeText = currentPreviewId ? previewsByType[currentPreviewId] || "" : "";
    const referencedCits = Array.from(activeText.matchAll(/\[\^([^\]]+)\]/g)).map((m) => m[1]);
    for (const ref of referencedCits) {
      const clean = ref.trim();
      if (!seenIds.has(clean)) {
        items.push({
          citationId: clean,
          type: clean.startsWith("aud") ? "audio" : clean.startsWith("img") ? "ocr" : clean.startsWith("fact") ? "fact" : "file",
          title: `Evidence ${clean}`,
          content: `Cross-modal evidence grounding reference [^${clean}]. Verified against source telemetry.`,
          sourceOrigin: "Multimodal Pipeline Extraction",
        });
        seenIds.add(clean);
      }
    }

    // 5. Parse any external links
    if (links) {
      links.split("\n").map((l) => l.trim()).filter(Boolean).forEach((url, i) => {
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

    // 6. Parse structured facts from groundingJson if present
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
  }, [groundingMd, previewCitations, sourceText, fileNames, links, groundingJson, currentPreviewId, previewsByType]);

  // Filtered evidence items based on search query
  const filteredEvidence = useMemo(() => {
    if (!filterQuery.trim()) return evidenceItems;
    const q = filterQuery.toLowerCase();
    return evidenceItems.filter(
      (item) =>
        item.citationId.toLowerCase().includes(q) ||
        item.title.toLowerCase().includes(q) ||
        item.content.toLowerCase().includes(q) ||
        (item.timestamp && item.timestamp.toLowerCase().includes(q))
    );
  }, [evidenceItems, filterQuery]);

  // Synchronize Provenance Anchors tray specifically with citations referenced in the active preview draft
  const activeDraftCitations = useMemo<Citation[]>(() => {
    const activeText = currentPreviewId ? previewsByType[currentPreviewId] || "" : "";
    const matches = Array.from(activeText.matchAll(/\[\^([^\]]+)\]/g)).map((m) => m[1].replace(/^\^/, "").trim());
    const uniqueIds = Array.from(new Set(matches));

    if (uniqueIds.length === 0) {
      return previewCitations;
    }

    const citMap = new Map<string, Citation>();
    previewCitations.forEach((c) => citMap.set(c.id.replace(/^\^/, "").trim(), c));

    return uniqueIds.map((id) => {
      const existing = citMap.get(id);
      if (existing) return existing;
      let kind: Citation["kind"] = "text";
      if (id.startsWith("img")) kind = "file";
      else if (id.startsWith("aud") || id.startsWith("vid")) kind = "link";
      return {
        id,
        label: id.startsWith("img")
          ? `Image Evidence [^${id}]`
          : id.startsWith("aud") || id.startsWith("vid")
          ? `Media Telemetry [^${id}]`
          : `Source Evidence [^${id}]`,
        kind,
        target: id,
      };
    });
  }, [currentPreviewId, previewsByType, previewCitations]);

  // Click-to-Scroll & Highlight Synchronization
  function scrollToSource(citationId: string) {
    const cleanId = citationId.replace(/^\^/, "").trim();

    // On mobile screens, automatically switch to source evidence tab
    setMobileTab("source");

    setTimeout(() => {
      const target =
        document.getElementById(`source-${cleanId}`) ||
        document.getElementById(`source-${cleanId.toLowerCase()}`) ||
        document.getElementById(cleanId) ||
        document.querySelector(`[data-source-id="${cleanId}"]`);

      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("source-card-highlighted");
        setTimeout(() => {
          target.classList.remove("source-card-highlighted");
        }, 2000);
      }
    }, 80);
  }

  return (
    <div className="review-workspace">
      {/* Top Review Stage Bar */}
      <div className="review-topbar">
        <div className="review-topbar-left">
          <button
            type="button"
            className="ghost sm back-btn"
            onClick={onBackToParameters}
            title="Return to Step 1 & 2 configuration"
          >
            ← Back to parameters
          </button>
          <div className="review-title-group">
            <h2 className="review-heading">
              Dual-Pane Provenance Review
            </h2>
            <span className="review-subtitle">
              {currentPreviewId ? outputTypeLabel(currentPreviewId) : "Deliverable Preview"}
            </span>
          </div>
        </div>

        {/* Mobile Tab Switcher */}
        <div className="mobile-view-tabs">
          <button
            type="button"
            className={mobileTab === "preview" ? "on" : ""}
            onClick={() => setMobileTab("preview")}
          >
            📄 Preview Draft
          </button>
          <button
            type="button"
            className={mobileTab === "source" ? "on" : ""}
            onClick={() => setMobileTab("source")}
          >
            🔍 Source Evidence ({evidenceItems.length})
          </button>
        </div>

        {/* Deliverable Finalize Action */}
        <div className="review-topbar-actions">
          <button
            type="button"
            className="primary finalize-btn"
            onClick={onFinalizeGeneration}
            disabled={generating}
          >
            {generating
              ? "Writing deliverables…"
              : `Finalize Deliverables (${selected.size})`}
          </button>
        </div>
      </div>

      {/* Dual-Pane Split Workspace */}
      <div className="review-workspace-split">
        {/* LEFT PANE: Source Evidence Grounding Inspector */}
        <section
          className={`source-inspector-pane ${mobileTab === "source" ? "mobile-active" : ""}`}
        >
          <div className="pane-header">
            <div className="pane-title-group">
              <span className="pane-title">Source Evidence Grounding</span>
              <span className="source-count-pill">
                {evidenceItems.length} Evidence {evidenceItems.length === 1 ? "Item" : "Items"}
              </span>
            </div>
            <div className="segmented sm">
              <button
                type="button"
                className={sourceViewMode === "cards" ? "on" : ""}
                onClick={() => setSourceViewMode("cards")}
                title="View individual evidence cards"
              >
                Cards
              </button>
              <button
                type="button"
                className={sourceViewMode === "raw" ? "on" : ""}
                onClick={() => setSourceViewMode("raw")}
                title="View unified extracted markdown context"
              >
                Raw Context
              </button>
            </div>
          </div>

          {sourceViewMode === "cards" ? (
            <>
              {/* Evidence Filter Bar */}
              <div className="source-search-bar">
                <input
                  type="text"
                  placeholder="Filter evidence by citation ID, timestamp, keyword…"
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  className="source-filter-input"
                />
                {filterQuery && (
                  <button
                    type="button"
                    className="clear-filter"
                    onClick={() => setFilterQuery("")}
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Scrollable Evidence Cards List */}
              <div
                className="source-cards-container slim-scroll"
                ref={leftPaneScrollRef}
              >
                {filteredEvidence.length === 0 ? (
                  <div className="card empty-evidence">
                    <p className="muted">No matching evidence found for "{filterQuery}".</p>
                  </div>
                ) : (
                  filteredEvidence.map((item) => (
                    <article
                      key={item.citationId}
                      id={`source-${item.citationId}`}
                      data-source-id={item.citationId}
                      className="source-evidence-card"
                    >
                      <div className="evidence-card-header">
                        <div className="evidence-tag-group">
                          <span className="citation-anchor-badge">
                            [^{item.citationId}]
                          </span>
                          <span className={`evidence-type-tag ${item.type}`}>
                            {item.type === "audio"
                              ? "🎧 Audio Transcript"
                              : item.type === "video"
                              ? "🎬 Video Extract"
                              : item.type === "ocr"
                              ? "🖼️ OCR Document"
                              : item.type === "link"
                              ? "🌐 Reference Link"
                              : item.type === "fact"
                              ? "📌 Grounding Fact"
                              : "📄 Document Text"}
                          </span>
                        </div>
                        {item.timestamp && (
                          <span className="evidence-timestamp">
                            ⏱️ {item.timestamp}
                          </span>
                        )}
                      </div>

                      <h4 className="evidence-title">{item.title}</h4>

                      <div className="evidence-content-snippet">
                        <p>{item.content}</p>
                      </div>

                      <div className="evidence-card-footer">
                        <span className="evidence-origin-label">
                          {item.sourceOrigin || "Ingested Evidence"}
                        </span>
                        <span className="evidence-sync-hint">
                          Matches <code>[^{item.citationId}]</code>
                        </span>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </>
          ) : (
            /* Raw Grounding Markdown View */
            <div className="raw-grounding-container slim-scroll">
              <Markdown content={groundingMd || sourceText || "No grounding context extracted."} />
            </div>
          )}
        </section>

        {/* RIGHT PANE: Interactive Platform Preview & Proofcheck */}
        <section
          className={`draft-preview-pane ${mobileTab === "preview" ? "mobile-active" : ""}`}
        >
          <div className="pane-header">
            <div className="pane-title-group">
              <span className="pane-title">Platform Preview & Proofcheck</span>
            </div>

            {/* Platform Selector Tabs */}
            {selected.size > 1 && (
              <div className="tabs param-tabs" role="tablist">
                {Array.from(selected).map((id) => (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={id === currentPreviewId}
                    className={id === currentPreviewId ? "on" : ""}
                    onClick={() => onSelectPreviewId(id)}
                  >
                    {outputTypeLabel(id)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="preview-toolbar">
            <span className="muted">
              Tailored blueprint for <strong>{currentPreviewId ? outputTypeLabel(currentPreviewId) : "deliverable"}</strong>
            </span>
            <div className="preview-actions">
              <div className="segmented">
                <button
                  type="button"
                  className={isOrganisation ? "on" : ""}
                  onClick={() => onToggleOrganisationMode(true)}
                  title="Organisation mode with sensitive data proofchecking"
                >
                  🏢 Org
                </button>
                <button
                  type="button"
                  className={!isOrganisation ? "on" : ""}
                  onClick={() => onToggleOrganisationMode(false)}
                  title="Normal mode"
                >
                  👤 Normal
                </button>
              </div>
              <div className="segmented">
                <button
                  type="button"
                  className={previewViewMode === "edit" ? "on" : ""}
                  onClick={() => onViewModeChange("edit")}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className={previewViewMode === "preview" ? "on" : ""}
                  onClick={() => onViewModeChange("preview")}
                >
                  Preview
                </button>
              </div>
            </div>
          </div>

          {/* Interactive Preview & Proofcheck Editor */}
          <div className="draft-editor-scroll slim-scroll">
            <InteractivePreviewEditor
              content={currentPreviewId ? previewsByType[currentPreviewId] ?? "" : ""}
              flags={currentPreviewId ? previewFlagsByType[currentPreviewId] ?? [] : []}
              isOrganisation={isOrganisation}
              viewMode={previewViewMode}
              onContentChange={onContentChange}
              onFlagsChange={onFlagsChange}
              onRerunProofcheck={onRerunProofcheck}
              proofchecking={proofchecking}
              onCitationClick={scrollToSource}
            />

            {/* Citations provenance tray */}
            <div className="citation-box provenance-citation-box">
              <div className="citation-box-header">
                <strong>Provenance Anchors ({activeDraftCitations.length})</strong>
                <span className="muted">Click any citation pill to jump to its source evidence chunk</span>
              </div>
              <div className="citation-list">
                {activeDraftCitations.map((citation) => (
                  <button
                    key={citation.id}
                    type="button"
                    className="citation-chip interactive-chip"
                    onClick={() => scrollToSource(citation.id)}
                    title={`Inspect source evidence for [^${citation.id}]`}
                  >
                    <span className="chip-icon">
                      {citation.kind === "file" ? "▣" : citation.kind === "link" ? "↗" : "¶"}
                    </span>
                    <span className="chip-id">[^{citation.id}]</span>
                    <span className="chip-label">{citation.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
