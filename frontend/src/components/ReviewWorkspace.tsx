import { useMemo, useState, useEffect } from "react";
import InteractivePreviewEditor from "./InteractivePreviewEditor";
import SourceEvidenceInspector from "./SourceEvidenceInspector";
import { outputTypeLabel } from "../lib/types";
import type { Citation, OutputTypeId, SensitiveDataFlag, EvidenceCardItem } from "../lib/types";
import { buildEvidenceItems, countCitationOccurrences } from "../lib/citations";

export type { EvidenceCardItem };

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
  onToggleOrganisationMode: _onToggleOrganisationMode,
  onRerunProofcheck,
  onFinalizeGeneration,
  onBackToParameters,
}: ReviewWorkspaceProps) {
  // Mobile responsive tab toggle ('preview' | 'source')
  const [mobileTab, setMobileTab] = useState<"preview" | "source">("preview");
  // Filter query in source inspector
  const [filterQuery, setFilterQuery] = useState("");
  // View mode in left pane ('cards' | 'visual')
  const [sourceViewMode, setSourceViewMode] = useState<"cards" | "visual">("cards");
  // Active visual item being inspected in image viewer
  const [activeVisualEvidence, setActiveVisualEvidence] = useState<EvidenceCardItem | null>(null);
  // Active highlighted bounding box citation ID (e.g. 'src-2', 'img-1')
  const [highlightedCitationId, setHighlightedCitationId] = useState<string | null>(null);
  // Focused occurrence index for multi-occurrence cycling
  const [focusedOccurrenceIndex, setFocusedOccurrenceIndex] = useState<number>(0);

  const activeDraftText = currentPreviewId ? previewsByType[currentPreviewId] || "" : "";

  // Parse structured source evidence items via unified builder
  const evidenceItems = useMemo<EvidenceCardItem[]>(() => {
    return buildEvidenceItems(
      groundingMd || "",
      previewCitations || [],
      sourceText || "",
      fileNames || [],
      links || "",
      groundingJson || null,
      activeDraftText
    );
  }, [groundingMd, previewCitations, sourceText, fileNames, links, groundingJson, activeDraftText]);

  // Visual evidence items (OCR diagrams, images, visual PDF pages)
  const visualEvidenceItems = useMemo(() => {
    return evidenceItems.filter((i) => i.type === "ocr" || i.bbox || i.mediaUrl);
  }, [evidenceItems]);

  // Keep active visual evidence synced when items load
  useEffect(() => {
    if (!activeVisualEvidence && visualEvidenceItems.length > 0) {
      setActiveVisualEvidence(visualEvidenceItems[0]);
    }
  }, [visualEvidenceItems, activeVisualEvidence]);

  // Total occurrences of the highlighted citation in the active preview draft
  const totalOccurrences = useMemo(() => {
    if (!highlightedCitationId) return 0;
    return countCitationOccurrences(activeDraftText, highlightedCitationId);
  }, [activeDraftText, highlightedCitationId]);

  // Occurrence cycle handlers
  function handleNextOccurrence() {
    if (totalOccurrences <= 0) return;
    setFocusedOccurrenceIndex((prev) => (prev + 1) % totalOccurrences);
  }

  function handlePrevOccurrence() {
    if (totalOccurrences <= 0) return;
    setFocusedOccurrenceIndex((prev) => (prev - 1 + totalOccurrences) % totalOccurrences);
  }

  function handleClearCitation() {
    setHighlightedCitationId(null);
    setFocusedOccurrenceIndex(0);
  }

  // Reverse linking: user clicked an evidence card or OCR bounding box in the left pane
  function handleSelectEvidence(citationId: string) {
    const cleanId = citationId.replace(/^\^/, "").trim();
    setHighlightedCitationId(cleanId);
    setFocusedOccurrenceIndex(0);
    // On mobile screens, automatically switch to preview draft tab
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setMobileTab("preview");
    }
  }

  // Forward linking: user clicked a citation pill or claim sentence inside the preview draft
  function scrollToSource(citationId: string) {
    const cleanId = citationId.replace(/^\^/, "").trim();
    setHighlightedCitationId(cleanId);
    setFocusedOccurrenceIndex(0);
    setMobileTab("source");

    // 1. Check if citation corresponds to visual image or OCR bounding box
    const targetVisual =
      visualEvidenceItems.find((v) => v.citationId.toLowerCase() === cleanId.toLowerCase()) ||
      visualEvidenceItems.find((v) =>
        (v.allBoxes || []).some((b) => b.id?.toLowerCase() === cleanId.toLowerCase())
      ) ||
      evidenceItems.find(
        (item) =>
          item.citationId.toLowerCase() === cleanId.toLowerCase() &&
          (item.type === "ocr" || item.bbox || item.mediaUrl)
      );

    if (targetVisual || cleanId.startsWith("img") || cleanId.startsWith("pdf-vis")) {
      const activeItem = targetVisual || (visualEvidenceItems.length > 0 ? visualEvidenceItems[0] : null);
      if (activeItem) {
        setSourceViewMode("visual");
        setActiveVisualEvidence(activeItem);
        return;
      }
    }

    // 2. If not visual, show in Cards view and scroll to target card
    if (sourceViewMode === "visual") {
      setSourceViewMode("cards");
    }

    setTimeout(() => {
      const target =
        document.getElementById(`source-${cleanId}`) ||
        document.getElementById(`source-${cleanId.toLowerCase()}`) ||
        document.getElementById(cleanId) ||
        document.querySelector(`[data-source-id="${cleanId}"]`);

      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 80);
  }

  // Synchronize Provenance Anchors tray specifically with citations referenced in the active preview draft
  const activeDraftCitations = useMemo<Citation[]>(() => {
    const matches = Array.from(activeDraftText.matchAll(/\[\^([^\]]+)\]/g)).map((m) =>
      m[1].replace(/^\^/, "").trim()
    );
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
      if (id.startsWith("img")) kind = "ocr";
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
  }, [activeDraftText, previewCitations]);

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
            <h2 className="review-heading">Dual-Pane Provenance Review</h2>
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
          </div>

          <SourceEvidenceInspector
            evidenceItems={evidenceItems}
            visualEvidenceItems={visualEvidenceItems}
            activeVisualEvidence={activeVisualEvidence || (visualEvidenceItems[0] ?? null)}
            highlightedCitationId={highlightedCitationId}
            sourceViewMode={sourceViewMode}
            groundingMd={groundingMd || ""}
            sourceText={sourceText || ""}
            filterQuery={filterQuery}
            activeDraftText={activeDraftText}
            onFilterChange={setFilterQuery}
            onViewModeChange={setSourceViewMode}
            onSelectVisualEvidence={setActiveVisualEvidence}
            onSelectEvidence={handleSelectEvidence}
          />
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
              Tailored blueprint for{" "}
              <strong>{currentPreviewId ? outputTypeLabel(currentPreviewId) : "deliverable"}</strong>
            </span>
            <div className="preview-actions">
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
              content={activeDraftText}
              flags={currentPreviewId ? previewFlagsByType[currentPreviewId] ?? [] : []}
              isOrganisation={isOrganisation}
              viewMode={previewViewMode}
              onContentChange={onContentChange}
              onFlagsChange={onFlagsChange}
              onRerunProofcheck={onRerunProofcheck}
              proofchecking={proofchecking}
              onCitationClick={scrollToSource}
              highlightedCitationId={highlightedCitationId}
              focusedOccurrenceIndex={focusedOccurrenceIndex}
              totalOccurrences={totalOccurrences}
              onNextOccurrence={handleNextOccurrence}
              onPrevOccurrence={handlePrevOccurrence}
              onClearCitation={handleClearCitation}
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
                    className={`citation-chip interactive-chip ${
                      highlightedCitationId?.toLowerCase() === citation.id.toLowerCase() ? "active" : ""
                    }`}
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
