import { useState, useMemo, useRef, useEffect } from "react";
import Markdown from "./Markdown";
import type { EvidenceCardItem, DetectedBoxItem } from "../lib/types";
import { countCitationOccurrences } from "../lib/citations";

interface SourceEvidenceInspectorProps {
  evidenceItems: EvidenceCardItem[];
  visualEvidenceItems: EvidenceCardItem[];
  activeVisualEvidence: EvidenceCardItem | null;
  highlightedCitationId: string | null;
  sourceViewMode: "cards" | "visual" | "raw";
  groundingMd: string;
  sourceText: string;
  filterQuery: string;
  activeDraftText?: string;
  onFilterChange: (q: string) => void;
  onViewModeChange: (mode: "cards" | "visual" | "raw") => void;
  onSelectVisualEvidence: (item: EvidenceCardItem) => void;
  onSelectEvidence: (citationId: string) => void;
}

export default function SourceEvidenceInspector({
  evidenceItems,
  visualEvidenceItems,
  activeVisualEvidence,
  highlightedCitationId,
  sourceViewMode,
  groundingMd,
  sourceText,
  filterQuery,
  activeDraftText = "",
  onFilterChange,
  onViewModeChange,
  onSelectVisualEvidence,
  onSelectEvidence,
}: SourceEvidenceInspectorProps) {
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [showAllBboxes, setShowAllBboxes] = useState<boolean>(true);
  const [selectedBoxItem, setSelectedBoxItem] = useState<DetectedBoxItem | null>(null);
  const leftPaneScrollRef = useRef<HTMLDivElement>(null);

  // Scroll to active card when highlightedCitationId changes externally
  useEffect(() => {
    if (!highlightedCitationId || sourceViewMode !== "cards") return;
    const clean = highlightedCitationId.replace(/^\^/, "").toLowerCase();
    const target =
      document.getElementById(`source-${clean}`) ||
      document.querySelector(`[data-source-id="${clean}"]`);

    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightedCitationId, sourceViewMode]);

  // Filter evidence cards
  const filteredEvidence = useMemo(() => {
    if (!filterQuery.trim()) return evidenceItems;
    const q = filterQuery.toLowerCase();
    return evidenceItems.filter(
      (item) =>
        item.citationId.toLowerCase().includes(q) ||
        item.title.toLowerCase().includes(q) ||
        item.content.toLowerCase().includes(q) ||
        item.meta?.toLowerCase().includes(q) ||
        item.sourceUrl?.toLowerCase().includes(q)
    );
  }, [evidenceItems, filterQuery]);

  return (
    <div className="source-inspector-wrapper">
      {/* View Mode Segmented Controls */}
      <div className="source-view-controls">
        <div className="segmented mode-switcher">
          <button
            type="button"
            className={sourceViewMode === "cards" ? "on" : ""}
            onClick={() => onViewModeChange("cards")}
          >
            📋 Evidence Cards ({evidenceItems.length})
          </button>
          <button
            type="button"
            className={sourceViewMode === "visual" ? "on" : ""}
            onClick={() => onViewModeChange("visual")}
          >
            🖼️ Visual Canvas ({visualEvidenceItems.length})
          </button>
        </div>
      </div>

      {sourceViewMode === "visual" ? (
        <div className="visual-evidence-pane">
          {/* Visual Evidence Toolbar */}
          <div className="visual-toolbar">
            <div className="visual-selector-group">
              <label htmlFor="visual-source-select" className="visual-select-label">
                Image / Visual Page:
              </label>
              <select
                id="visual-source-select"
                className="visual-select"
                value={activeVisualEvidence?.citationId || ""}
                onChange={(e) => {
                  const selectedItem = visualEvidenceItems.find((v) => v.citationId === e.target.value);
                  if (selectedItem) {
                    onSelectVisualEvidence(selectedItem);
                    setSelectedBoxItem(null);
                  }
                }}
              >
                {visualEvidenceItems.map((v) => (
                  <option key={v.citationId} value={v.citationId}>
                    {v.title || `Visual Source ${v.citationId}`} ({v.allBoxes?.length || 1} boxes)
                  </option>
                ))}
              </select>
            </div>

            <div className="visual-zoom-controls">
              <button
                type="button"
                className="ghost sm zoom-btn"
                onClick={() => setZoomLevel((z) => Math.max(50, z - 15))}
                title="Zoom Out"
              >
                −
              </button>
              <span className="zoom-label">{zoomLevel}%</span>
              <button
                type="button"
                className="ghost sm zoom-btn"
                onClick={() => setZoomLevel((z) => Math.min(250, z + 15))}
                title="Zoom In"
              >
                +
              </button>
              <button
                type="button"
                className="ghost sm zoom-btn"
                onClick={() => setZoomLevel(100)}
                title="Reset Zoom to 100%"
              >
                100%
              </button>
              <button
                type="button"
                className={`ghost sm toggle-bboxes-btn ${showAllBboxes ? "active" : ""}`}
                onClick={() => setShowAllBboxes((v) => !v)}
                title="Toggle All Detected OCR Boxes"
              >
                {showAllBboxes ? "Hide Other Boxes" : "Show All Boxes"}
              </button>
            </div>
          </div>



          {/* Interactive Image & Bounding Box Viewport */}
          <div className="visual-stage-viewport slim-scroll">
            <div
              className="visual-stage-canvas"
              style={{
                transform: `scale(${zoomLevel / 100})`,
                transformOrigin: "top center",
              }}
            >
              <div className="visual-image-wrapper">
                <img
                  src={activeVisualEvidence?.mediaUrl || "/api/pipeline/media/default/1.png"}
                  alt={activeVisualEvidence?.title || "Visual Evidence"}
                  className="visual-stage-image"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).src = "/api/pipeline/media/default/1.png";
                  }}
                />

                {/* Bounding Boxes Layer */}
                <div className="visual-bboxes-overlay">
                  {/* 1. All detected boxes */}
                  {showAllBboxes &&
                    (activeVisualEvidence?.allBoxes || []).map((box, bIdx) => {
                      const isTarget =
                        highlightedCitationId &&
                        (box.id?.toLowerCase() === highlightedCitationId.toLowerCase() ||
                          activeVisualEvidence?.citationId.toLowerCase() === highlightedCitationId.toLowerCase());
                      if (isTarget) return null;

                      const isSelected = selectedBoxItem?.id === box.id;

                      return (
                        <div
                          key={box.id || `box-${bIdx}`}
                          className={`ocr-bbox ${isSelected ? "selected" : ""}`}
                          style={{
                            left: `calc(${box.bbox.x}% - 6px)`,
                            top: `calc(${box.bbox.y}% - 4px)`,
                            width: `calc(${box.bbox.width}% + 12px)`,
                            height: `calc(${box.bbox.height}% + 8px)`,
                          }}
                          onClick={() => {
                            setSelectedBoxItem(box);
                            const boxCitId = box.id || activeVisualEvidence?.citationId || "";
                            if (boxCitId) onSelectEvidence(boxCitId);
                          }}
                          title={`OCR text: "${box.text}" — Click to link bidirectionally`}
                        >
                          <div className="ocr-bbox-tooltip">
                            <span className="ocr-bbox-tooltip-text">{box.text}</span>
                            {box.conf && (
                              <span className="ocr-bbox-conf">({Math.round(box.conf)}% conf)</span>
                            )}
                          </div>
                        </div>
                      );
                    })}

                  {/* 2. Targeted / Cited Active Bounding Box */}
                  {activeVisualEvidence?.bbox && (
                    <div
                      className="ocr-bbox highlighted-active-box"
                      style={{
                        left: `calc(${activeVisualEvidence.bbox.x}% - 8px)`,
                        top: `calc(${activeVisualEvidence.bbox.y}% - 6px)`,
                        width: `calc(${activeVisualEvidence.bbox.width}% + 16px)`,
                        height: `calc(${activeVisualEvidence.bbox.height}% + 12px)`,
                      }}
                      onClick={() => activeVisualEvidence && onSelectEvidence(activeVisualEvidence.citationId)}
                      title="Click to locate referencing claim sentence in deliverable"
                    >
                      <div className="highlight-pill-tag">
                        [^{highlightedCitationId || activeVisualEvidence.citationId}]
                      </div>
                      <div className="active-bbox-callout">
                        <strong>Ground-Truth OCR Extraction:</strong>
                        <p>{activeVisualEvidence.content || activeVisualEvidence.title}</p>
                        <span className="bbox-link-cta">📍 Click box to jump to claim in deliverable →</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Selected Box Drawer */}
          {selectedBoxItem && (
            <div className="selected-box-drawer">
              <div className="drawer-header">
                <strong>Selected OCR Box</strong>
                <button
                  type="button"
                  className="ghost sm"
                  onClick={() => setSelectedBoxItem(null)}
                >
                  ✕
                </button>
              </div>
              <p className="drawer-text">"{selectedBoxItem.text}"</p>
              <div className="drawer-meta">
                <span>
                  Confidence: {selectedBoxItem.conf ? `${Math.round(selectedBoxItem.conf)}%` : "High"}
                </span>
                <span>
                  Coordinates: ({Math.round(selectedBoxItem.bbox.x)}%, {Math.round(selectedBoxItem.bbox.y)}%)
                </span>
                <button
                  type="button"
                  className="primary sm jump-box-btn"
                  onClick={() => onSelectEvidence(selectedBoxItem.id || activeVisualEvidence?.citationId || "src-1")}
                >
                  📍 Locate Claim in Deliverable →
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Evidence Filter Bar */}
          <div className="source-search-bar">
            <input
              type="text"
              placeholder="Filter evidence by citation ID, timestamp, keyword…"
              value={filterQuery}
              onChange={(e) => onFilterChange(e.target.value)}
              className="source-filter-input"
            />
            {filterQuery && (
              <button
                type="button"
                className="clear-filter"
                onClick={() => onFilterChange("")}
              >
                ✕
              </button>
            )}
          </div>

          {/* Scrollable Evidence Cards List */}
          <div className="source-cards-container slim-scroll" ref={leftPaneScrollRef}>
            {filteredEvidence.length === 0 ? (
              <div className="card empty-evidence">
                <p className="muted">No matching evidence found for "{filterQuery}".</p>
              </div>
            ) : (
              filteredEvidence.map((item) => {
                const isSelected =
                  highlightedCitationId &&
                  item.citationId.toLowerCase() === highlightedCitationId.toLowerCase();

                const occurrencesInDraft = countCitationOccurrences(activeDraftText, item.citationId);

                return (
                  <article
                    key={item.citationId}
                    id={`source-${item.citationId.toLowerCase()}`}
                    data-source-id={item.citationId}
                    className="source-evidence-card"
                    onClick={() => onSelectEvidence(item.citationId)}
                  >
                    <div className="evidence-card-header">
                      <div className="evidence-tag-group">
                        <span
                          className="citation-anchor-badge"
                          title="Click to jump to claim in deliverable"
                        >
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

                    {/* Visual Coordinates and Jump Button if item has BBox */}
                    {(item.bbox || item.mediaUrl) && (
                      <div className="evidence-visual-action-bar">
                        {item.bbox && (
                          <span className="evidence-coords-chip">
                            📍 ({Math.round(item.bbox.x)}%, {Math.round(item.bbox.y)}%) •{" "}
                            {Math.round(item.bbox.width)}%×{Math.round(item.bbox.height)}%
                          </span>
                        )}
                        <button
                          type="button"
                          className="ghost sm inspect-visual-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectVisualEvidence(item);
                            onViewModeChange("visual");
                          }}
                          title="Inspect in image canvas"
                        >
                          🔍 View in Image Canvas →
                        </button>
                      </div>
                    )}

                    <div className="evidence-card-footer">
                      <span className="evidence-origin-label">
                        {item.sourceOrigin || "Ingested Evidence"}
                      </span>
                      <div className="card-reverse-nav">
                        {occurrencesInDraft > 0 ? (
                          <span className="draft-occurrence-pill">
                            ✓ Cited {occurrencesInDraft}× in draft
                          </span>
                        ) : (
                          <span className="draft-occurrence-pill uncited">
                            Uncited in this view
                          </span>
                        )}
                        <button
                          type="button"
                          className="card-jump-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectEvidence(item.citationId);
                          }}
                          title={`Jump to claim referencing [^${item.citationId}]`}
                        >
                          Find Claim ↗
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}
