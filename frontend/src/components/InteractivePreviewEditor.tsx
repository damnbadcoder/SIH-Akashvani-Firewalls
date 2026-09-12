import { useMemo, useState, useRef, useEffect } from "react";
import Markdown from "./Markdown";
import type { SensitiveDataFlag } from "../lib/types";

interface InteractivePreviewEditorProps {
  content: string;
  flags: SensitiveDataFlag[];
  isOrganisation: boolean;
  viewMode: "edit" | "preview";
  onContentChange: (newContent: string) => void;
  onFlagsChange: (newFlags: SensitiveDataFlag[]) => void;
  onRerunProofcheck: () => void;
  proofchecking: boolean;
  onCitationClick?: (citationId: string) => void;
}

export default function InteractivePreviewEditor({
  content,
  flags,
  isOrganisation,
  viewMode,
  onContentChange,
  onFlagsChange,
  onRerunProofcheck,
  proofchecking,
  onCitationClick,
}: InteractivePreviewEditorProps) {
  const [activeFlagId, setActiveFlagId] = useState<string | null>(null);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close popover when clicking outside or pressing Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setActiveFlagId(null);
        setPopoverPos(null);
      }
    }
    function handleClickOutside(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        !(e.target as HTMLElement).closest(".sensitive-flag-badge")
      ) {
        setActiveFlagId(null);
        setPopoverPos(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Sorted flags
  const sortedFlags = useMemo(() => {
    return [...flags].sort((a, b) => a.char_start - b.char_start);
  }, [flags]);

  // Risk counters
  const criticalCount = useMemo(
    () => flags.filter((f) => f.severity === "CRITICAL").length,
    [flags]
  );
  const highOrMedCount = useMemo(
    () => flags.filter((f) => f.severity !== "CRITICAL").length,
    [flags]
  );

  // Active flag object
  const activeFlag = useMemo(
    () => flags.find((f) => f.flag_id === activeFlagId) ?? null,
    [flags, activeFlagId]
  );

  // Mask / Redact single flag
  function redactFlag(flag: SensitiveDataFlag) {
    let start = flag.char_start;
    let end = flag.char_end;
    if (flag.matched_text && content.slice(start, end) !== flag.matched_text) {
      const idx = content.indexOf(flag.matched_text);
      if (idx !== -1) {
        start = idx;
        end = idx + flag.matched_text.length;
      }
    }
    const replacement = `[REDACTED: ${flag.entity_type}]`;
    const before = content.slice(0, start);
    const after = content.slice(end);
    const newContent = before + replacement + after;
    const delta = replacement.length - (end - start);

    const updatedFlags = flags
      .filter((f) => f.flag_id !== flag.flag_id)
      .map((f) => {
        if (f.char_start > start) {
          return {
            ...f,
            char_start: f.char_start + delta,
            char_end: f.char_end + delta,
          };
        }
        return f;
      });

    onContentChange(newContent);
    onFlagsChange(updatedFlags);
    setActiveFlagId(null);
    setPopoverPos(null);
  }

  // Accept / Keep single flag
  function acceptFlag(flag: SensitiveDataFlag) {
    const updatedFlags = flags.filter((f) => f.flag_id !== flag.flag_id);
    onFlagsChange(updatedFlags);
    setActiveFlagId(null);
    setPopoverPos(null);
  }

  // Delete / Strip single flag
  function deleteFlag(flag: SensitiveDataFlag) {
    let start = flag.char_start;
    let end = flag.char_end;
    if (flag.matched_text && content.slice(start, end) !== flag.matched_text) {
      const idx = content.indexOf(flag.matched_text);
      if (idx !== -1) {
        start = idx;
        end = idx + flag.matched_text.length;
      }
    }
    const before = content.slice(0, start);
    const after = content.slice(end);
    const newContent = before + after;
    const delta = -(end - start);

    const updatedFlags = flags
      .filter((f) => f.flag_id !== flag.flag_id)
      .map((f) => {
        if (f.char_start > start) {
          return {
            ...f,
            char_start: f.char_start + delta,
            char_end: f.char_end + delta,
          };
        }
        return f;
      });

    onContentChange(newContent);
    onFlagsChange(updatedFlags);
    setActiveFlagId(null);
    setPopoverPos(null);
  }

  // Redact All flags in one click
  function redactAll() {
    if (flags.length === 0) return;
    // Process in descending order of char_start to preserve preceding offsets
    const descending = [...flags].sort((a, b) => b.char_start - a.char_start);
    let updatedText = content;
    for (const flag of descending) {
      let start = flag.char_start;
      let end = flag.char_end;
      if (flag.matched_text && updatedText.slice(start, end) !== flag.matched_text) {
        const idx = updatedText.indexOf(flag.matched_text);
        if (idx !== -1) {
          start = idx;
          end = idx + flag.matched_text.length;
        }
      }
      const replacement = `[REDACTED: ${flag.entity_type}]`;
      updatedText =
        updatedText.slice(0, start) +
        replacement +
        updatedText.slice(end);
    }
    onContentChange(updatedText);
    onFlagsChange([]);
    setActiveFlagId(null);
    setPopoverPos(null);
  }

  // Ignore All flags in one click
  function ignoreAll() {
    onFlagsChange([]);
    setActiveFlagId(null);
    setPopoverPos(null);
  }

  // Handle inline badge click inside preview pane
  function handlePreviewContainerClick(e: React.MouseEvent<HTMLDivElement>) {
    // 1. Citation pill click: triggers scroll and highlight on source evidence pane
    const citTarget = (e.target as HTMLElement).closest("[data-citation-id]") as HTMLElement | null;
    if (citTarget) {
      const citId = citTarget.getAttribute("data-citation-id");
      if (citId && onCitationClick) {
        onCitationClick(citId);
      }
      return;
    }

    // 2. Sensitive flag badge click: opens operator decision popover
    const target = (e.target as HTMLElement).closest(".sensitive-flag-badge, .sensitive-flag") as HTMLElement | null;
    if (!target) return;

    const flagId = target.getAttribute("data-flag-id");
    if (!flagId) return;

    if (activeFlagId === flagId) {
      setActiveFlagId(null);
      setPopoverPos(null);
      return;
    }

    const containerRect = containerRef.current?.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();

    if (containerRect) {
      const top = targetRect.bottom - containerRect.top + 8;
      const left = Math.max(10, Math.min(targetRect.left - containerRect.left, containerRect.width - 340));
      setPopoverPos({ top, left });
      setActiveFlagId(flagId);
    }
  }

  // Prepare display markdown for Preview Mode by annotating flags and citation tags with HTML
  const annotatedMarkdown = useMemo(() => {
    let result = content;

    // 1. If Organisation mode is active, annotate sensitive flags in reverse order
    if (isOrganisation && sortedFlags.length > 0) {
      const descending = [...sortedFlags].sort((a, b) => b.char_start - a.char_start);
      for (const flag of descending) {
        let start = flag.char_start;
        let end = flag.char_end;
        let matched = "";

        if (start >= 0 && end <= result.length && start < end) {
          matched = result.slice(start, end);
        }

        if (flag.matched_text && matched !== flag.matched_text) {
          const idx = result.indexOf(flag.matched_text);
          if (idx !== -1) {
            start = idx;
            end = idx + flag.matched_text.length;
            matched = flag.matched_text;
          }
        }

        if (!matched && flag.matched_text) {
          matched = flag.matched_text;
        }

        if (start < 0 || end > result.length || start >= end || !matched.trim()) {
          continue;
        }

        const sevClass = (flag.severity || "HIGH").toLowerCase();
        const replacement = `<span class="sensitive-flag sensitive-flag-badge ${sevClass} soc-review-badge" data-flag-id="${flag.flag_id}" title="Sensitive ${flag.entity_type} (${flag.severity}) - Click to review"><span class="badge-icon">🛡️</span> <span class="flag-matched-value">${matched}</span> <span class="flag-review-pill">Review</span></span>`;
        result = result.slice(0, start) + replacement + result.slice(end);
      }
    }

    // 2. Render operator-redacted tokens as clean, neutral muted badges
    result = result.replace(
      /\[REDACTED(?::\s*[^\]]+)?\]|\[RESTRICTED\]/g,
      (match) => `<span class="redacted-pill-badge" title="Redacted by operator">${match}</span>`
    );

    // 3. Annotate citation markers like [^src-1], [^aud-1], [^img-1] as interactive pills
    result = result.replace(
      /\[\^((?:src|aud|vid|img|doc|fact|[a-zA-Z0-9_\-]+)-\d+|[^\]]+)\]/gi,
      (_match, citationId) => {
        return `<button type="button" class="citation-pill" data-citation-id="${citationId}" title="Jump to source evidence [^${citationId}]"><span class="citation-icon">↗</span> [^${citationId}]</button>`;
      }
    );

    return result;
  }, [content, sortedFlags, isOrganisation]);

  return (
    <div className="interactive-preview-wrapper" ref={containerRef}>
      {/* Sensitivity Proofchecker Toolbar */}
      {isOrganisation && (
        <div className="sensitivity-toolbar">
          <div className="risk-counters">
            <span className="toolbar-label">🛡️ Audit:</span>
            {flags.length === 0 ? (
              <span className="risk-badge clean">✓ 0 Sensitive Items Found</span>
            ) : (
              <>
                {criticalCount > 0 && (
                  <span className="risk-badge critical">
                    🚨 {criticalCount} Critical
                  </span>
                )}
                {highOrMedCount > 0 && (
                  <span className="risk-badge high">
                    ⚠️ {highOrMedCount} High/Medium
                  </span>
                )}
              </>
            )}
          </div>

          <div className="toolbar-actions">
            {flags.length > 0 && (
              <>
                <button
                  type="button"
                  className="btn-redact-all"
                  onClick={redactAll}
                  title="Redact all flagged sensitive entities"
                >
                  🛡️ Redact All Flags ({flags.length})
                </button>
                <button
                  type="button"
                  className="ghost sm"
                  onClick={ignoreAll}
                  title="Accept all flagged items as-is"
                >
                  ✓ Ignore All
                </button>
              </>
            )}
            <button
              type="button"
              className="ghost sm"
              onClick={onRerunProofcheck}
              disabled={proofchecking}
              title="Re-run offline deterministic sensitivity scan"
            >
              {proofchecking ? "Scanning…" : "🔄 Re-check"}
            </button>
          </div>
        </div>
      )}

      {/* Editor or Preview Pane */}
      {viewMode === "edit" ? (
        <textarea
          className="md-editor preview-editor"
          value={content}
          onChange={(e) => onContentChange(e.target.value)}
          placeholder="Edit your markdown blueprint draft here…"
        />
      ) : (
        <div
          className="preview-rendered-pane interactive-pane"
          onClick={handlePreviewContainerClick}
        >
          <Markdown content={annotatedMarkdown} />
        </div>
      )}

      {/* Floating Action Popover for Inline Flag Inspection */}
      {activeFlag && popoverPos && (
        <div
          className="flag-popover-card"
          ref={popoverRef}
          style={{ top: `${popoverPos.top}px`, left: `${popoverPos.left}px` }}
        >
          <div className="popover-header">
            <div className="popover-title">
              <span className={`severity-tag ${activeFlag.severity.toLowerCase()}`}>
                {activeFlag.severity}
              </span>
              <strong>{activeFlag.entity_type}</strong>
            </div>
            <button
              type="button"
              className="close-popover"
              onClick={() => {
                setActiveFlagId(null);
                setPopoverPos(null);
              }}
            >
              ✕
            </button>
          </div>

          <div className="popover-body">
            <div className="matched-text-preview">
              <code>{activeFlag.matched_text}</code>
            </div>
            <p className="popover-hint">
              Choose an operator action for this sensitive item:
            </p>
          </div>

          <div className="popover-actions">
            <button
              type="button"
              className="popover-btn redact"
              onClick={() => redactFlag(activeFlag)}
              title="Replace with redacted placeholder"
            >
              🛡️ Redact / Mask
            </button>
            <button
              type="button"
              className="popover-btn accept"
              onClick={() => acceptFlag(activeFlag)}
              title="Accept original text"
            >
              ✓ Accept (Keep)
            </button>
            <button
              type="button"
              className="popover-btn delete"
              onClick={() => deleteFlag(activeFlag)}
              title="Delete sensitive text completely"
            >
              ✕ Delete
            </button>
          </div>
        </div>
      )}

      {/* Active Flags Tray: Accessible in both Edit & Preview modes */}
      {isOrganisation && flags.length > 0 && (
        <div className="flags-tray-container">
          <div className="flags-tray-header">
            <strong>Active Flagged Items ({flags.length})</strong>
            <span className="muted">Click an action below or click an inline badge above</span>
          </div>
          <div className="flags-tray-list">
            {sortedFlags.map((flag) => (
              <div key={flag.flag_id} className={`flags-tray-item ${flag.severity.toLowerCase()}`}>
                <div className="flag-item-info">
                  <span className={`severity-badge-sm ${flag.severity.toLowerCase()}`}>
                    {flag.severity}
                  </span>
                  <span className="flag-item-type">{flag.entity_type}:</span>
                  <code className="flag-item-value">{flag.matched_text}</code>
                </div>
                <div className="flag-item-buttons">
                  <button
                    type="button"
                    className="tray-btn redact"
                    onClick={() => redactFlag(flag)}
                    title="Redact with [REDACTED]"
                  >
                    Redact
                  </button>
                  <button
                    type="button"
                    className="tray-btn accept"
                    onClick={() => acceptFlag(flag)}
                    title="Accept and keep text"
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    className="tray-btn delete"
                    onClick={() => deleteFlag(flag)}
                    title="Delete text"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
