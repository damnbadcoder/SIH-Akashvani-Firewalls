import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import Markdown from "../components/Markdown";
import ReviewWorkspace from "../components/ReviewWorkspace";
import { logoutUser } from "../lib/firebase";
import {
  generateDeliverable,
  generatePlan,
  proofcheckPreviewDraft,
  proofcheckSensitiveLocal,
  regenerateDeliverable,
  autosavePreviewDraft,
  fetchUserHistory,
  reSignDeliverableApi,
} from "../lib/mock";
import {
  AUDIENCE_CATEGORIES,
  DEFAULT_PARAMS,
  DETAIL_LEVELS,
  LANGUAGES,
  OBJECTIVES,
  OUTPUT_TYPES,
  TONES,
  outputTypeLabel,
} from "../lib/types";
import type {
  Citation,
  Deliverable,
  Generation,
  GenerationParams,
  OutputTypeId,
  PlatformPreview,
  SensitiveDataFlag,
  User,
} from "../lib/types";

function getAccountHistoryKey(email?: string): string {
  return email ? `tx.history.${email}` : "tx.history.anonymous";
}

function loadHistoryForAccount(email?: string): Generation[] {
  try {
    return JSON.parse(localStorage.getItem(getAccountHistoryKey(email)) ?? "[]") as Generation[];
  } catch {
    return [];
  }
}

function copyParams(params: GenerationParams): GenerationParams {
  return { ...params };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const user = useMemo<User | null>(() => {
    try {
      return JSON.parse(localStorage.getItem("tx.user") ?? "null") as User | null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!user) navigate("/login", { replace: true });
  }, [user, navigate]);

  const [sourceTab, setSourceTab] = useState<"text" | "files" | "links">("text");
  const [sourceText, setSourceText] = useState("");
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [links, setLinks] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const [isOrganisation, setIsOrganisation] = useState<boolean>(() => {
    return user?.userType === "Organisation";
  });

  const [selected, setSelected] = useState<Set<OutputTypeId>>(new Set());
  const [paramsByType, setParamsByType] = useState<Partial<Record<OutputTypeId, GenerationParams>>>({});
  const [openParams, setOpenParams] = useState<OutputTypeId | null>(null);

  const [planning, setPlanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [previewsByType, setPreviewsByType] = useState<Partial<Record<OutputTypeId, string>>>({});
  const [previewFlagsByType, setPreviewFlagsByType] = useState<Partial<Record<OutputTypeId, SensitiveDataFlag[]>>>({});
  const [previewsData, setPreviewsData] = useState<Record<string, PlatformPreview>>({});
  const [groundingMd, setGroundingMd] = useState<string>("");
  const [groundingJson, setGroundingJson] = useState<any>(null);
  const [activePreviewId, setActivePreviewId] = useState<OutputTypeId | null>(null);
  const [previewCitations, setPreviewCitations] = useState<Citation[]>([]);
  const [previewViewMode, setPreviewViewMode] = useState<"edit" | "preview">("preview");
  const [proofchecking, setProofchecking] = useState<boolean>(false);
  const [gen, setGen] = useState<Generation | null>(null);
  const [activeId, setActiveId] = useState<OutputTypeId | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [history, setHistory] = useState<Generation[]>(() => loadHistoryForAccount(user?.email));
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [refinement, setRefinement] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [showSigModal, setShowSigModal] = useState(false);
  const hasAutoRestored = useRef(false);
  const autosaveTimeout = useRef<any>(null);

  function restoreBlueprintSession(item: Generation) {
    const sId = item.sessionId || item.id;
    setSessionId(sId);
    setSourceText(item.sourceText || "");
    setFileNames(item.fileNames || []);
    setUploadedFiles([]);
    setLinks((item.links || []).join("\n"));

    const outputIds: OutputTypeId[] =
      item.selectedOutputs && item.selectedOutputs.length > 0
        ? item.selectedOutputs
        : (Object.keys(item.previewsByType || {}) as OutputTypeId[]);

    setSelected(new Set(outputIds));
    setParamsByType(item.paramsByType || {});
    setPreviewsByType(item.previewsByType || {});
    setPreviewsData(item.previews || {});
    setGroundingMd(item.groundingMd || item.sourceText || "");
    setGroundingJson(item.groundingJson || null);
    setPreviewCitations(item.citations || []);
    setActivePreviewId(outputIds[0] || null);
    if (item.isOrganisation !== undefined) {
      setIsOrganisation(item.isOrganisation);
    }
    setGen(null);
    setEditing(false);
    setDraft("");
    setGenError("");
    setPreviewViewMode("preview");
  }

  useEffect(() => {
    if (!user?.email) return;
    let isMounted = true;
    const historyKey = getAccountHistoryKey(user.email);

    async function syncAccountHistory() {
      const local = loadHistoryForAccount(user?.email);
      if (isMounted) setHistory(local);

      const remote = await fetchUserHistory(user?.email, user?.id);
      if (!isMounted) return;

      const map = new Map<string, Generation>();
      for (const item of local) {
        map.set(item.sessionId || item.id, item);
      }
      for (const item of remote) {
        const key = item.sessionId || item.id;
        const prev = map.get(key);
        map.set(key, { ...prev, ...item });
      }

      const merged = Array.from(map.values()).sort((a, b) => b.createdAt - a.createdAt);
      setHistory(merged);
      localStorage.setItem(historyKey, JSON.stringify(merged));

      // Auto-restore latest in-progress blueprint preview directly on Dashboard launch/login
      if (!hasAutoRestored.current && merged.length > 0) {
        const latest = merged[0];
        if (latest.status === "blueprint_ready") {
          hasAutoRestored.current = true;
          restoreBlueprintSession(latest);
        }
      }
    }

    syncAccountHistory();
    return () => { isMounted = false; };
  }, [user?.email, user?.id]);

  const active: Deliverable | undefined = gen?.deliverables.find(
    (d) => d.outputType === activeId
  );
  const isPreviewStage = (Object.keys(previewsByType).length > 0 || planning) && !gen;
  const isReviewMode = Object.keys(previewsByType).length > 0 && !gen;
  const currentStage: 1 | 2 | 3 = gen ? 3 : isPreviewStage ? 2 : 1;
  const activeParamId: OutputTypeId | null =
    openParams && selected.has(openParams)
      ? openParams
      : selected.size > 0
      ? Array.from(selected)[0]
      : null;

  const currentPreviewId: OutputTypeId | null =
    activePreviewId && selected.has(activePreviewId)
      ? activePreviewId
      : selected.size > 0
      ? Array.from(selected)[0]
      : null;

  function startNewTransformation() {
    setSessionId(null);
    setGen(null);
    setPreviewsByType({});
    setPreviewsData({});
    setActivePreviewId(null);
    setSelected(new Set());
    setParamsByType({});
    setOpenParams(null);
    setSourceText("");
    setFileNames([]);
    setUploadedFiles([]);
    setLinks("");
    setPreviewCitations([]);
    setGroundingMd("");
    setGroundingJson(null);
    setEditing(false);
    setDraft("");
    setRefinement("");
    setGenError("");
    setPreviewViewMode("preview");
    setPreviewFlagsByType({});
  }

  function paramsFor(id: OutputTypeId): GenerationParams {
    return paramsByType[id] ?? copyParams(DEFAULT_PARAMS);
  }

  function updateParams(id: OutputTypeId, patch: Partial<GenerationParams>) {
    setParamsByType((prev) => ({
      ...prev,
      [id]: { ...paramsFor(id), ...patch },
    }));
  }

  function toggleOutput(id: OutputTypeId) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        if (openParams === id) {
          const remaining = Array.from(next);
          setOpenParams(remaining.length > 0 ? remaining[0] : null);
        }
        if (activePreviewId === id) {
          const remaining = Array.from(next);
          setActivePreviewId(remaining.length > 0 ? remaining[0] : null);
        }
      } else {
        next.add(id);
        setOpenParams(id);
        if (!activePreviewId) {
          setActivePreviewId(id);
        }
      }
      return next;
    });
  }

  function sourceSummary(g: Generation): string {
    const parts: string[] = [];
    if (g.sourceText.trim()) parts.push(`${g.sourceText.trim().length.toLocaleString()} chars of text`);
    if (g.fileNames.length) parts.push(`${g.fileNames.length} file(s)`);
    if (g.links.length) parts.push(`${g.links.length} link(s)`);
    return parts.join(" · ") || "empty source";
  }

  async function createPreview() {
    setGenError("");
    const hasText = sourceText.trim().length > 0;
    const hasFiles = fileNames.length > 0 || uploadedFiles.length > 0;
    const sourceLinks = links.split("\n").map((link) => link.trim()).filter(Boolean);
    if (!hasText && !hasFiles && sourceLinks.length === 0) {
      setGenError("Provide source content — paste text, upload files or add links.");
      return;
    }
    if (selected.size === 0) {
      setGenError("Select at least one output type.");
      return;
    }

    setPlanning(true);
    try {
      const filesToPass = uploadedFiles.length > 0 ? uploadedFiles : fileNames;
      const result = await generatePlan(
        sourceText,
        filesToPass,
        sourceLinks,
        Array.from(selected).map((id) => ({ id, params: paramsFor(id) })),
        isOrganisation,
        user?.email,
        user?.id,
        sessionId || undefined
      );

      const activeSessionId = result.sessionId || sessionId || crypto.randomUUID();
      setSessionId(activeSessionId);
      setPreviewsByType(result.previewsByType);
      setPreviewsData(result.previews || {});
      setGroundingMd(result.groundingMd || sourceText);
      setGroundingJson(result.groundingJson || null);
      const first = Array.from(selected)[0];
      setActivePreviewId(first);
      setPreviewCitations(result.citations);
      setGen(null);

      // Add to history ONLY once blueprint preview is created
      const draftGen: Generation = {
        id: activeSessionId,
        sessionId: activeSessionId,
        status: "blueprint_ready",
        selectedOutputs: Array.from(selected),
        createdAt: Date.now(),
        sourceText,
        fileNames,
        links: sourceLinks,
        paramsByType: Object.fromEntries(
          Array.from(selected).map((id) => [id, paramsFor(id)])
        ) as Record<OutputTypeId, GenerationParams>,
        previewsByType: { ...result.previewsByType },
        previews: { ...result.previews },
        plan: first ? result.previewsByType[first] : "",
        citations: result.citations,
        deliverables: [],
        groundingMd: result.groundingMd || sourceText,
        groundingJson: result.groundingJson || null,
        isOrganisation,
      };

      setHistory((prev) => {
        const filtered = prev.filter((item) => (item.sessionId || item.id) !== activeSessionId);
        const updated = [draftGen, ...filtered].slice(0, 30);
        localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(updated));
        return updated;
      });

      // Populate initial structured flags from previews
      const initialFlags: Partial<Record<OutputTypeId, SensitiveDataFlag[]>> = {};
      if (result.previews) {
        for (const [key, pObj] of Object.entries(result.previews)) {
          const matchingId = Array.from(selected).find(
            (id) =>
              id === pObj.output_type_id ||
              id === pObj.platform_key ||
              outputTypeLabel(id) === key
          );
          if (matchingId && pObj.sensitive_flags) {
            initialFlags[matchingId] = pObj.sensitive_flags;
          }
        }
      }
      setPreviewFlagsByType(initialFlags);
    } catch (err: any) {
      setGenError(err?.message || "Failed to generate previews. Please ensure the backend server is running.");
    } finally {
      setPlanning(false);
    }
  }

  function updateActivePreview(text: string) {
    if (!currentPreviewId) return;
    const updated = {
      ...previewsByType,
      [currentPreviewId]: text,
    };
    setPreviewsByType(updated);

    // Debounced autosave to backend and local history
    if (sessionId) {
      if (autosaveTimeout.current) clearTimeout(autosaveTimeout.current);
      autosaveTimeout.current = setTimeout(() => {
        autosavePreviewDraft(sessionId, currentPreviewId, text);
        setHistory((prev) => {
          const next = prev.map((item) => {
            if ((item.sessionId || item.id) === sessionId) {
              return {
                ...item,
                previewsByType: { ...(item.previewsByType || {}), [currentPreviewId]: text },
              };
            }
            return item;
          });
          localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(next));
          return next;
        });
      }, 1000);
    }
  }

  function updateActivePreviewFlags(newFlags: SensitiveDataFlag[]) {
    if (!currentPreviewId) return;
    setPreviewFlagsByType((prev) => ({
      ...prev,
      [currentPreviewId]: newFlags,
    }));
  }

  // Keep flags accurately synced when switching to Preview mode
  useEffect(() => {
    if (previewViewMode === "preview" && isOrganisation && currentPreviewId && previewsByType[currentPreviewId]) {
      const local = proofcheckSensitiveLocal(previewsByType[currentPreviewId]!);
      setPreviewFlagsByType((prev) => ({
        ...prev,
        [currentPreviewId]: local.flags,
      }));
    }
  }, [previewViewMode, currentPreviewId, isOrganisation]);

  async function toggleOrganisationMode(enabled: boolean) {
    setIsOrganisation(enabled);
    if (!isPreviewStage) return;

    if (!enabled) {
      setPreviewFlagsByType({});
      return;
    }

    setProofchecking(true);
    try {
      const updatedFlags: Partial<Record<OutputTypeId, SensitiveDataFlag[]>> = {};
      for (const id of selected) {
        const text = previewsByType[id] || "";
        const res = await proofcheckPreviewDraft(text, groundingMd, groundingJson, false);
        updatedFlags[id] = res.flags;
      }
      setPreviewFlagsByType(updatedFlags);
    } finally {
      setProofchecking(false);
    }
  }

  async function rerunProofcheck() {
    if (!currentPreviewId || !previewsByType[currentPreviewId]) return;
    setProofchecking(true);
    try {
      const res = await proofcheckPreviewDraft(
        previewsByType[currentPreviewId]!,
        groundingMd,
        groundingJson,
        false
      );
      setPreviewFlagsByType((prev) => ({
        ...prev,
        [currentPreviewId]: res.flags,
      }));
    } finally {
      setProofchecking(false);
    }
  }

  async function finalizeGeneration() {
    setGenError("");
    setGenerating(true);
    const sourceLinks = links.split("\n").map((link) => link.trim()).filter(Boolean);

    // Operator-approved, clean text with resolved redactions is passed directly
    const verifiedPreviews: Partial<Record<OutputTypeId, string>> = { ...previewsByType };
    const currentSessionId = sessionId || crypto.randomUUID();

    const g: Generation = {
      id: currentSessionId,
      sessionId: currentSessionId,
      status: "completed",
      selectedOutputs: Array.from(selected),
      createdAt: Date.now(),
      sourceText,
      fileNames,
      links: sourceLinks,
      paramsByType: Object.fromEntries(
        Array.from(selected).map((id) => [id, paramsFor(id)])
      ) as Record<OutputTypeId, GenerationParams>,
      previewsByType: { ...verifiedPreviews },
      previews: { ...previewsData },
      plan: currentPreviewId ? verifiedPreviews[currentPreviewId] : "",
      citations: previewCitations,
      deliverables: [],
      groundingMd,
      groundingJson,
      isOrganisation,
    };

    try {
      const first = selected.values().next().value as OutputTypeId;
      for (const id of selected) {
        const res = await generateDeliverable(
          id,
          sourceText,
          paramsFor(id),
          verifiedPreviews[id],
          isOrganisation,
          groundingMd,
          groundingJson,
          currentSessionId,
          user?.email,
          user?.id
        );
        const contentStr = typeof res === "string" ? res : res.content;
        g.deliverables.push({
          outputType: id,
          content: contentStr,
          retries: 0,
          deliverable_id: typeof res === "object" ? res.deliverable_id : undefined,
          signature: typeof res === "object" ? res.signature : undefined,
          signing_key_id: typeof res === "object" ? res.signing_key_id : undefined,
          content_hash: typeof res === "object" ? res.content_hash : undefined,
          signature_envelope: typeof res === "object" ? res.signature_envelope : undefined,
          qr_data_url: typeof res === "object" ? res.qr_data_url : undefined,
          verification_url: typeof res === "object" ? res.verification_url : undefined,
          revision: typeof res === "object" ? (res.revision || 1) : 1,
        });
        setGen({ ...g, deliverables: [...g.deliverables] });
        if (id === first) setActiveId(id);
      }
      const done: Generation = { ...g, deliverables: [...g.deliverables], status: "completed" };
      setHistory((prev) => {
        const filtered = prev.filter((item) => (item.sessionId || item.id) !== currentSessionId);
        const nextHistory = [done, ...filtered].slice(0, 30);
        localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(nextHistory));
        return nextHistory;
      });
      setPreviewsByType({});
      setPreviewsData({});
      setActivePreviewId(null);
      setPreviewCitations([]);
      setOpenParams(null);
    } catch {
      setGenError("The model could not create the deliverables. Please try again.");
    } finally {
      setGenerating(false);
    }
  }

  async function retry() {
    if (!gen || !active || !activeId) return;
    setRetrying(true);
    try {
      const content = await regenerateDeliverable(
        activeId,
        gen.sourceText,
        paramsFor(activeId),
        refinement || "Improve overall quality and clarity"
      );
      setGen({
        ...gen,
        deliverables: gen.deliverables.map((d) =>
          d.outputType === activeId ? { ...d, content, retries: d.retries + 1 } : d
        ),
      });
    } finally {
      setRetrying(false);
    }
  }

  function openHistory(item: Generation) {
    const isBlueprint = item.status === "blueprint_ready" || (!item.deliverables || item.deliverables.length === 0);
    if (isBlueprint) {
      restoreBlueprintSession(item);
    } else {
      setSessionId(item.sessionId || item.id);
      setGen(item);
      setPreviewsByType(item.previewsByType || {});
      setActivePreviewId(null);
      setPreviewCitations(item.citations);
      setActiveId(item.deliverables[0]?.outputType ?? null);
      setSelected(new Set(item.deliverables.map((d) => d.outputType)));
      setParamsByType(item.paramsByType);
      setSourceText(item.sourceText);
      setFileNames(item.fileNames);
      setLinks(item.links.join("\n"));
      setEditing(false);
      setOpenParams(null);
    }
    setHistoryOpen(false);
  }

  async function acceptDraft() {
    if (!gen || !activeId || !active) return;
    let updatedDeliverable: Deliverable = {
      ...active,
      content: draft,
      retries: active.retries + 1,
    };

    if (active.deliverable_id) {
      try {
        const reSignRes = await reSignDeliverableApi(active.deliverable_id, draft);
        if (reSignRes) {
          updatedDeliverable = {
            ...updatedDeliverable,
            signature: reSignRes.signature,
            signing_key_id: reSignRes.signing_key_id,
            content_hash: reSignRes.content_hash,
            signature_envelope: reSignRes.signature_envelope,
            qr_data_url: reSignRes.qr_data_url,
            verification_url: reSignRes.verification_url,
            revision: reSignRes.revision,
          };
        }
      } catch (err) {
        console.warn("Could not re-sign on deliverable edit:", err);
      }
    }

    setGen({
      ...gen,
      deliverables: gen.deliverables.map((d) =>
        d.outputType === activeId ? updatedDeliverable : d
      ),
    });
    setEditing(false);
  }

  async function copy() {
    if (!active) return;
    await navigator.clipboard.writeText(active.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function download() {
    if (!active) return;
    const blob = new Blob([active.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${active.outputType}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function downloadSidecar() {
    if (!active) return;
    const envelope = active.signature_envelope || {
      format: "transmute-signature-v1",
      deliverable_id: active.deliverable_id || gen?.sessionId || "local-draft",
      output_type: active.outputType,
      signature: active.signature || "unsigned",
      content_sha256: active.content_hash || "none",
      signing_key_id: active.signing_key_id || "transmute-key-2026-v1",
      revision: active.revision || 1,
      verification_url: active.verification_url || `${window.location.origin}/verify?id=${active.deliverable_id}&hash=${active.content_hash}`,
    };
    const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${active.outputType}_rev${active.revision || 1}.sig`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function logout() {
    await logoutUser();
    navigate("/login", { replace: true });
  }

  if (!user) return null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <button
            type="button"
            className="ghost sm history-toggle"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label="Toggle history"
          >
            <span className="history-icon">☰</span>
            {history.length > 0 && <span className="history-badge">{history.length}</span>}
          </button>
          <div className="brand"><span className="logo-mark sm">⌁</span> Transmute</div>
        </div>

        <nav className="stage-stepper" aria-label="Transformation Progress">
          <div className={`step-node ${currentStage === 1 ? "active" : "completed"}`}>
            <span className="step-num">1</span>
            <span className="step-label">Ingest & Configure</span>
          </div>
          <span className="step-divider" aria-hidden="true">→</span>
          <div className={`step-node ${currentStage === 2 ? "active" : currentStage > 2 ? "completed" : "pending"}`}>
            <span className="step-num">2</span>
            <span className="step-label">Blueprint Approval</span>
          </div>
          <span className="step-divider" aria-hidden="true">→</span>
          <div className={`step-node ${currentStage === 3 ? "active" : "pending"}`}>
            <span className="step-num">3</span>
            <span className="step-label">Deliverables</span>
          </div>
        </nav>

        <div className="topbar-right">
          <Link
            to="/verify"
            className="ghost sm verify-nav-link"
            title="Open Public Deliverable Authenticity & Watermark Verifier"
            style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "var(--text)", textDecoration: "none" }}
          >
            🛡️ <span>Verify Authenticity</span>
          </Link>
          {user.photoURL && (
            <img
              src={user.photoURL}
              alt={user.name}
              className="topbar-avatar"
              referrerPolicy="no-referrer"
            />
          )}
          <span className="user-chip">{user.name} · <em>{user.userType}</em></span>
          <button className="ghost sm" onClick={logout}>Sign out</button>
        </div>
      </header>

      {historyOpen && (
        <div className="drawer-backdrop" onClick={() => setHistoryOpen(false)} aria-hidden="true" />
      )}

      <aside className={`history-drawer ${historyOpen ? "open" : ""}`}>
        <div className="drawer-header">
          <h3>History</h3>
          <button className="ghost sm" onClick={() => setHistoryOpen(false)}>✕</button>
        </div>

        <div className="sidebar-user">
          <div className="avatar">
            {user.photoURL ? (
              <img
                src={user.photoURL}
                alt={user.name}
                className="avatar-img"
                referrerPolicy="no-referrer"
              />
            ) : (
              user.name.slice(0, 1).toUpperCase()
            )}
          </div>
          <div><strong>{user.name}</strong><span>{user.email}</span><span>{user.organisation || user.userType}</span></div>
        </div>

        <button className="primary sm" onClick={() => { startNewTransformation(); setHistoryOpen(false); }} style={{ width: "100%" }}>
          + New Transformation
        </button>

        {history.length === 0 ? (
          <p className="muted sidebar-empty">No generations yet.</p>
        ) : (
          <ul className="history-list">
            {history.map((item) => {
              const isBlueprint = item.status === "blueprint_ready" || (!item.deliverables || item.deliverables.length === 0);
              const label =
                item.deliverables && item.deliverables.length > 0
                  ? item.deliverables.map((d) => outputTypeLabel(d.outputType)).join(", ")
                  : item.selectedOutputs && item.selectedOutputs.length > 0
                  ? item.selectedOutputs.map((id) => outputTypeLabel(id)).join(", ")
                  : item.previewsByType && Object.keys(item.previewsByType).length > 0
                  ? Object.keys(item.previewsByType).map((id) => outputTypeLabel(id as OutputTypeId)).join(", ")
                  : "Blueprint Draft";

              return (
                <li key={item.sessionId || item.id}>
                  <button onClick={() => openHistory(item)}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", width: "100%" }}>
                      <strong>{label}</strong>
                      <span className={`status-tag ${isBlueprint ? "blueprint" : "completed"}`}>
                        {isBlueprint ? "Blueprint Ready" : "Completed"}
                      </span>
                    </div>
                    <span className="muted">
                      {new Date(item.createdAt).toLocaleDateString()} · {sourceSummary(item)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>

      <div className={`workspace ${isReviewMode ? "review-layout" : ""}`}>
        {isReviewMode ? (
          <ReviewWorkspace
            currentPreviewId={currentPreviewId}
            selected={selected}
            previewsByType={previewsByType}
            previewFlagsByType={previewFlagsByType}
            previewCitations={previewCitations}
            sourceText={sourceText}
            fileNames={fileNames}
            links={links}
            groundingMd={groundingMd}
            groundingJson={groundingJson}
            isOrganisation={isOrganisation}
            previewViewMode={previewViewMode}
            generating={generating}
            proofchecking={proofchecking}
            onSelectPreviewId={setActivePreviewId}
            onViewModeChange={setPreviewViewMode}
            onContentChange={updateActivePreview}
            onFlagsChange={updateActivePreviewFlags}
            onToggleOrganisationMode={toggleOrganisationMode}
            onRerunProofcheck={rerunProofcheck}
            onFinalizeGeneration={finalizeGeneration}
            onBackToParameters={() => {
              setPreviewsByType({});
              setActivePreviewId(null);
            }}
          />
        ) : (
          <>
            <main className="col-input">
          <h2 className="col-title">1 · Source content</h2>
          <div className="card">
            <div className="segmented full">
              {(["text", "files", "links"] as const).map((tab) => (
                <button key={tab} className={sourceTab === tab ? "on" : ""} onClick={() => setSourceTab(tab)}>
                  {tab === "text" ? "Text / Prompt" : tab[0].toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>
            {sourceTab === "text" && <textarea className="source-text" placeholder="Paste an article, report, advisory, incident note, or a free-form prompt…" value={sourceText} onChange={(e) => setSourceText(e.target.value)} rows={12} />}
            {sourceTab === "files" && (
              <div className="dropzone">
                <button className="ghost" onClick={() => fileInput.current?.click()}>Attach files</button>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  hidden
                  accept=".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.mp4,.mov,.webm,.wav,.mp3"
                  onChange={(e) => {
                    const newFiles = Array.from(e.target.files ?? []);
                    setFileNames((prev) => [...new Set([...prev, ...newFiles.map((file) => file.name)])]);
                    setUploadedFiles((prev) => {
                      const existingNames = new Set(prev.map((f) => f.name));
                      return [...prev, ...newFiles.filter((f) => !existingNames.has(f.name))];
                    });
                  }}
                />
                <p className="muted">PDF · DOCX · images · video · audio · plain text</p>
                {fileNames.length > 0 && (
                  <ul className="file-list">
                    {fileNames.map((name) => (
                      <li key={name}>
                        {name}
                        <button
                          className="x"
                          onClick={() => {
                            setFileNames((prev) => prev.filter((item) => item !== name));
                            setUploadedFiles((prev) => prev.filter((f) => f.name !== name));
                          }}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {sourceTab === "links" && <textarea className="source-text" placeholder={"https://example.org/threat-report\nhttps://news.example.com/breach"} value={links} onChange={(e) => setLinks(e.target.value)} rows={6} />}
          </div>

          <h2 className="col-title">2 · Output types <span className="muted">({selected.size} selected)</span></h2>
          <div className="card output-grid">
            {OUTPUT_TYPES.map((type) => {
              const chosen = selected.has(type.id);
              const configuring = chosen && activeParamId === type.id;
              return (
                <button
                  key={type.id}
                  className={`output-tile ${chosen ? "on" : ""} ${configuring ? "configuring" : ""}`}
                  onClick={() => toggleOutput(type.id)}
                >
                  <strong>{type.label}</strong>
                  <span>{type.hint}</span>
                  {chosen && <small>{configuring ? "Configuring" : "Selected"}</small>}
                </button>
              );
            })}
          </div>
          {!gen && (
            <button className="primary generate" onClick={createPreview} disabled={planning}>
              {planning ? "Preparing preview…" : `Create editable preview${selected.size ? ` · ${selected.size} output${selected.size === 1 ? "" : "s"}` : ""}`}
            </button>
          )}
          {gen && (
            <button className="ghost generate" onClick={startNewTransformation}>
              + Start new transformation
            </button>
          )}
          {genError && <p className="form-error">{genError}</p>}
        </main>

        <section className="col-output">
          {/* STAGE 1: Parameters beside Source Content (Visible before preview is requested or during planning) */}
          {!gen && (
            <>
              <div className="section-header">
                <h2 className="col-title">
                  3 · Parameters {activeParamId ? `— ${outputTypeLabel(activeParamId)}` : ""}
                </h2>
              </div>

              {planning ? (
                <div className="card empty">
                  <p className="pulse">Analysing source context and synthesizing tailored blueprints…</p>
                </div>
              ) : (
                <>
                  <div className="mode-toggle-card">
                    <div className="mode-toggle-header">
                      <strong>Auditing & Verification Mode</strong>
                      <span className={`mode-badge ${isOrganisation ? "org" : "normal"}`}>
                        {isOrganisation ? "Organisation Active" : "Normal Mode"}
                      </span>
                    </div>
                    <div className="segmented full">
                      <button
                        type="button"
                        className={isOrganisation ? "on" : ""}
                        onClick={() => toggleOrganisationMode(true)}
                      >
                        🏢 Organisation
                      </button>
                      <button
                        type="button"
                        className={!isOrganisation ? "on" : ""}
                        onClick={() => toggleOrganisationMode(false)}
                      >
                        👤 Normal / Someone
                      </button>
                    </div>
                    <p className="mode-hint">
                      {isOrganisation
                        ? "🛡️ Secondary proofchecking active: Scans and highlights operational leaks (internal IPs, credentials, classified entities, PII) in red before final deliverable generation."
                        : "Standard synthesis: Direct blueprint without sensitive highlight inspection."}
                    </p>
                  </div>

                  {selected.size === 0 ? (
                    <div className="card empty">
                      <p>No output types selected.</p>
                      <p className="muted">
                        Select one or more output types in Step 2 to configure audience, tone, detail level, and language.
                      </p>
                    </div>
                  ) : (
                    <>
                      {selected.size > 1 && (
                        <div className="tabs param-tabs" role="tablist">
                          {Array.from(selected).map((id) => (
                            <button
                              key={id}
                              role="tab"
                              aria-selected={id === activeParamId}
                              className={id === activeParamId ? "on" : ""}
                              onClick={() => setOpenParams(id)}
                            >
                              {outputTypeLabel(id)}
                            </button>
                          ))}
                        </div>
                      )}

                      {activeParamId && (
                        <div className="card param-grid">
                          <label>
                            Audience category
                            <select
                              value={paramsFor(activeParamId).audienceCategory}
                              onChange={(e) =>
                                updateParams(activeParamId, {
                                  audienceCategory: e.target.value as GenerationParams["audienceCategory"],
                                })
                              }
                            >
                              {AUDIENCE_CATEGORIES.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Target audience <span className="opt">(optional)</span>
                            <input
                              placeholder="e.g. bank CISOs, district collectors"
                              value={paramsFor(activeParamId).targetAudience}
                              onChange={(e) =>
                                updateParams(activeParamId, { targetAudience: e.target.value })
                              }
                            />
                          </label>
                          <label>
                            Tone
                            <select
                              value={paramsFor(activeParamId).tone}
                              onChange={(e) =>
                                updateParams(activeParamId, {
                                  tone: e.target.value as GenerationParams["tone"],
                                })
                              }
                            >
                              {TONES.map((tone) => (
                                <option key={tone} value={tone}>
                                  {tone}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Level of detail
                            <select
                              value={paramsFor(activeParamId).detail}
                              onChange={(e) =>
                                updateParams(activeParamId, {
                                  detail: e.target.value as GenerationParams["detail"],
                                })
                              }
                            >
                              {DETAIL_LEVELS.map((detail) => (
                                <option key={detail} value={detail}>
                                  {detail}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Objective
                            <select
                              value={paramsFor(activeParamId).objective}
                              onChange={(e) =>
                                updateParams(activeParamId, {
                                  objective: e.target.value as GenerationParams["objective"],
                                })
                              }
                            >
                              {OBJECTIVES.map((objective) => (
                                <option key={objective} value={objective}>
                                  {objective}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Language
                            <select
                              value={paramsFor(activeParamId).language}
                              onChange={(e) =>
                                updateParams(activeParamId, { language: e.target.value })
                              }
                            >
                              {LANGUAGES.map((language) => (
                                <option key={language} value={language}>
                                  {language}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}

          {/* STAGE 3: Deliverables (Visible after final generation) */}
          {gen && (
            <>
              <div className="section-header">
                <h2 className="col-title">3 · Deliverables</h2>
                <button
                  className="ghost sm"
                  onClick={startNewTransformation}
                >
                  + New transformation
                </button>
              </div>
              <div className="result-meta">
                <span>{sourceSummary(gen)}</span>
                <span className="muted">{new Date(gen.createdAt).toLocaleString()}</span>
              </div>
              <div className="tabs" role="tablist">
                {gen.deliverables.map((item) => (
                  <button
                    key={item.outputType}
                    role="tab"
                    aria-selected={item.outputType === activeId}
                    className={item.outputType === activeId ? "on" : ""}
                    onClick={() => { setActiveId(item.outputType); setEditing(false); }}
                  >
                    {outputTypeLabel(item.outputType)}
                    {item.retries > 0 && <sup>{item.retries}</sup>}
                  </button>
                ))}
              </div>
              {active && (
                <div className="card deliverable">
                  <div className="deliverable-toolbar">
                    <button
                      type="button"
                      className="sig-badge-btn"
                      onClick={() => setShowSigModal(true)}
                      title="Inspect Ed25519 Notary Seal & QR Watermark"
                    >
                      <span className="sig-icon">🛡️</span>
                      <span className="sig-text">
                        {active.signature ? "Signed & Authentic" : "Cryptographic Seal"}
                      </span>
                      {active.revision && active.revision > 1 && (
                        <span className="sig-rev">Rev #{active.revision}</span>
                      )}
                    </button>
                    {editing ? (
                      <>
                        <button className="ghost sm" onClick={() => setEditing(false)}>Discard</button>
                        <button className="primary sm" onClick={acceptDraft}>Save changes & Re-sign</button>
                      </>
                    ) : (
                      <>
                        <button className="ghost sm" onClick={() => { setDraft(active.content); setEditing(true); }}>Edit markdown</button>
                        <button className="ghost sm" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
                        <button className="ghost sm" onClick={download}>Download .md</button>
                        <button className="ghost sm" onClick={downloadSidecar} title="Download detached .sig cryptographic sidecar">Download .sig</button>
                      </>
                    )}
                  </div>
                  {editing ? (
                    <textarea className="md-editor" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
                  ) : (
                    <Markdown content={active.content} />
                  )}
                </div>
              )}
              {active && !editing && (
                <div className="card retry">
                  <strong>Not satisfied?</strong>
                  <textarea placeholder="Describe what to change — e.g. “shorter, drop the jargon, add a call to action”" value={refinement} onChange={(e) => setRefinement(e.target.value)} rows={2} />
                  <button className="primary" onClick={retry} disabled={retrying}>
                    {retrying ? "Regenerating…" : "Retry with this instruction"}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
          </>
        )}
      </div>

      {/* T9: Signature & Watermark Modal */}
      {showSigModal && active && (
        <div className="sig-modal-overlay" onClick={() => setShowSigModal(false)}>
          <div className="sig-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="sig-modal-header">
              <h3>
                <span>🛡️</span> Deliverable Notary Seal & Provenance
              </h3>
              <button
                type="button"
                className="sig-modal-close"
                onClick={() => setShowSigModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="sig-seal-banner">
              <span>✓</span>
              <div>
                <strong>Cryptographically Sealed Deliverable</strong>
                <p style={{ margin: 0, fontSize: "12px", opacity: 0.9 }}>
                  Signed using asymmetric <strong>Ed25519</strong> over the canonical SHA-256 deliverable digest.
                </p>
              </div>
            </div>

            {/* QR Code Watermark & Scan info */}
            <div className="sig-qr-container">
              {active.qr_data_url ? (
                <img
                  src={active.qr_data_url}
                  alt="Deliverable Verification QR Code"
                  className="sig-qr-img"
                />
              ) : (
                <div className="sig-qr-img" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "#000", fontSize: "11px", textAlign: "center" }}>
                  QR Watermark Available
                </div>
              )}
              <div className="sig-qr-meta">
                <strong>Scannable Verification Watermark</strong>
                <span className="muted">
                  Recipients can scan this QR code with any mobile camera to immediately verify authenticity against the platform ledger.
                </span>
                <Link
                  to={`/verify?id=${active.deliverable_id || ""}&hash=${active.content_hash || ""}`}
                  className="ghost sm"
                  style={{ alignSelf: "flex-start", marginTop: "4px" }}
                >
                  Open Verification Portal ↗
                </Link>
              </div>
            </div>

            {/* Metadata breakdown */}
            <div className="sig-meta-grid">
              <div className="sig-meta-item">
                <span className="sig-meta-label">Deliverable ID</span>
                <span className="sig-meta-value">{active.deliverable_id || "Local Draft"}</span>
              </div>
              <div className="sig-meta-item">
                <span className="sig-meta-label">Revision</span>
                <span className="sig-meta-value">Rev #{active.revision || 1}</span>
              </div>
              <div className="sig-meta-item">
                <span className="sig-meta-label">Signer Key ID</span>
                <span className="sig-meta-value">{active.signing_key_id || "transmute-key-2026-v1"}</span>
              </div>
              <div className="sig-meta-item">
                <span className="sig-meta-label">Classification</span>
                <span className="sig-meta-value">TLP:AMBER+STRICT</span>
              </div>
            </div>

            {active.content_hash && (
              <div className="sig-meta-item">
                <span className="sig-meta-label">SHA-256 Content Digest</span>
                <code style={{ fontSize: "11px", wordBreak: "break-all", background: "rgba(0,0,0,0.3)", padding: "6px", borderRadius: "4px" }}>
                  {active.content_hash}
                </code>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "8px" }}>
              <button type="button" className="ghost sm" onClick={downloadSidecar}>
                Download .sig Sidecar
              </button>
              <button type="button" className="primary sm" onClick={() => setShowSigModal(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
