import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Markdown from "../components/Markdown";
import ReviewWorkspace from "../components/ReviewWorkspace";
import SourceEvidenceInspector from "../components/SourceEvidenceInspector";
import { logoutUser } from "../lib/firebase";
import {
  generateDeliverableWithMeta,
  generatePlan,
  proofcheckPreviewDraft,
  proofcheckSensitiveLocal,
  regenerateDeliverable,
  autosavePreviewDraft,
  fetchUserHistory,
  scrapeLink,
  triggerFileDownload,
  exportDeliverableFile,
  exportDeliverablesZip,
  translateDeliverable,
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
  EvidenceCardItem,
  Generation,
  GenerationParams,
  OutputTypeId,
  PlatformPreview,
  SensitiveDataFlag,
  User,
  ScrapedLinkData,
} from "../lib/types";
import {
  annotateBidirectionalCitations,
  buildEvidenceItems,
  countCitationOccurrences,
} from "../lib/citations";

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
  const [linkInput, setLinkInput] = useState("");
  const [scrapedLinks, setScrapedLinks] = useState<ScrapedLinkData[]>([]);
  const [scrapingLink, setScrapingLink] = useState(false);
  const [scrapingError, setScrapingError] = useState("");
  const [linksInputMode, setLinksInputMode] = useState<"card" | "raw">("card");
  const [viewingArtifact, setViewingArtifact] = useState<{
    type: "md" | "json";
    title: string;
    filename: string;
    content: string;
  } | null>(null);
  const [copiedArtifact, setCopiedArtifact] = useState(false);
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
  const [singleDownloadOpen, setSingleDownloadOpen] = useState(false);
  const [batchDownloadOpen, setBatchDownloadOpen] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);
  const singleDropdownRef = useRef<HTMLDivElement>(null);
  const batchDropdownRef = useRef<HTMLDivElement>(null);
  const [translatingLang, setTranslatingLang] = useState(false);
  const [originalEnglishByOutput, setOriginalEnglishByOutput] = useState<Partial<Record<OutputTypeId, string>>>({});
  const hasAutoRestored = useRef(false);
  const autosaveTimeout = useRef<any>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (singleDropdownRef.current && !singleDropdownRef.current.contains(target)) {
        setSingleDownloadOpen(false);
      }
      if (batchDropdownRef.current && !batchDropdownRef.current.contains(target)) {
        setBatchDownloadOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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

  // Stage 3 Bidirectional Source Evidence Grounding state
  const [showEvidencePanel, setShowEvidencePanel] = useState<boolean>(false);
  const [stage3HighlightedCitationId, setStage3HighlightedCitationId] = useState<string | null>(null);
  const [stage3FocusedOccurrenceIndex, setStage3FocusedOccurrenceIndex] = useState<number>(0);
  const [stage3FilterQuery, setStage3FilterQuery] = useState<string>("");
  const [stage3SourceViewMode, setStage3SourceViewMode] = useState<"cards" | "visual" | "raw">("cards");
  const [stage3ActiveVisual, setStage3ActiveVisual] = useState<EvidenceCardItem | null>(null);
  const deliverableContentRef = useRef<HTMLDivElement>(null);

  // Stage 3 Structured Evidence Items
  const stage3EvidenceItems = useMemo<EvidenceCardItem[]>(() => {
    if (!gen) return [];
    return buildEvidenceItems(
      gen.groundingMd || groundingMd || "",
      gen.citations || previewCitations || [],
      gen.sourceText || sourceText || "",
      gen.fileNames || fileNames || [],
      (gen.links || []).join("\n") || links || "",
      gen.groundingJson || groundingJson || null,
      active?.content || ""
    );
  }, [gen, groundingMd, previewCitations, sourceText, fileNames, links, groundingJson, active?.content]);

  const stage3VisualEvidenceItems = useMemo(() => {
    return stage3EvidenceItems.filter((i) => i.type === "ocr" || i.bbox || i.mediaUrl);
  }, [stage3EvidenceItems]);

  // Keep active visual synced in stage 3
  useEffect(() => {
    if (!stage3ActiveVisual && stage3VisualEvidenceItems.length > 0) {
      setStage3ActiveVisual(stage3VisualEvidenceItems[0]);
    }
  }, [stage3VisualEvidenceItems, stage3ActiveVisual]);

  // Stage 3 Citation occurrence counts in the active deliverable
  const stage3TotalOccurrences = useMemo(() => {
    if (!stage3HighlightedCitationId || !active?.content) return 0;
    return countCitationOccurrences(active.content, stage3HighlightedCitationId);
  }, [active?.content, stage3HighlightedCitationId]);

  // Stage 3 annotated deliverable markdown
  const stage3AnnotatedContent = useMemo(() => {
    if (!active?.content) return "";
    return annotateBidirectionalCitations(
      active.content,
      stage3HighlightedCitationId,
      stage3FocusedOccurrenceIndex
    );
  }, [active?.content, stage3HighlightedCitationId, stage3FocusedOccurrenceIndex]);

  // Stage 3 occurrence cycling handlers
  function handleStage3NextOccurrence() {
    if (stage3TotalOccurrences <= 0) return;
    setStage3FocusedOccurrenceIndex((prev) => (prev + 1) % stage3TotalOccurrences);
  }

  function handleStage3PrevOccurrence() {
    if (stage3TotalOccurrences <= 0) return;
    setStage3FocusedOccurrenceIndex((prev) => (prev - 1 + stage3TotalOccurrences) % stage3TotalOccurrences);
  }

  function handleStage3ClearCitation() {
    setStage3HighlightedCitationId(null);
    setStage3FocusedOccurrenceIndex(0);
  }

  // Reverse linking in Stage 3: clicked card or OCR box in the evidence inspector
  function handleStage3SelectEvidence(citationId: string) {
    const cleanId = citationId.replace(/^\^/, "").trim();
    setStage3HighlightedCitationId(cleanId);
    setStage3FocusedOccurrenceIndex(0);
  }

  // Forward linking in Stage 3: clicked citation pill or claim sentence inside deliverable
  function scrollToStage3Source(citationId: string) {
    const cleanId = citationId.replace(/^\^/, "").trim();
    setStage3HighlightedCitationId(cleanId);
    setStage3FocusedOccurrenceIndex(0);
    setShowEvidencePanel(true);

    const targetVisual =
      stage3VisualEvidenceItems.find((v) => v.citationId.toLowerCase() === cleanId.toLowerCase()) ||
      stage3VisualEvidenceItems.find((v) =>
        (v.allBoxes || []).some((b) => b.id?.toLowerCase() === cleanId.toLowerCase())
      ) ||
      stage3EvidenceItems.find(
        (item) =>
          item.citationId.toLowerCase() === cleanId.toLowerCase() &&
          (item.type === "ocr" || item.bbox || item.mediaUrl)
      );

    if (targetVisual || cleanId.startsWith("img") || cleanId.startsWith("pdf-vis")) {
      const activeItem = targetVisual || (stage3VisualEvidenceItems.length > 0 ? stage3VisualEvidenceItems[0] : null);
      if (activeItem) {
        setStage3SourceViewMode("visual");
        setStage3ActiveVisual(activeItem);
        return;
      }
    }

    if (stage3SourceViewMode === "visual") {
      setStage3SourceViewMode("cards");
    }

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

  // Auto-scroll deliverable content to focused occurrence when citation or occurrence changes
  useEffect(() => {
    if (!stage3HighlightedCitationId || !deliverableContentRef.current) return;
    const cleanId = stage3HighlightedCitationId.replace(/^\^/, "").trim().toLowerCase();
    const matches = deliverableContentRef.current.querySelectorAll(
      `[data-citation-ref="${cleanId}"]`
    );
    if (matches && matches.length > 0) {
      const idx = Math.min(stage3FocusedOccurrenceIndex, matches.length - 1);
      matches[idx]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [stage3HighlightedCitationId, stage3FocusedOccurrenceIndex]);

  // Click handler inside Stage 3 deliverable container for citation pills & claims
  function handleStage3DeliverableClick(e: React.MouseEvent<HTMLDivElement>) {
    const citTarget = (e.target as HTMLElement).closest("[data-citation-id], [data-citation-ref]") as HTMLElement | null;
    if (citTarget) {
      const citId = citTarget.getAttribute("data-citation-id") || citTarget.getAttribute("data-citation-ref");
      if (citId) {
        scrollToStage3Source(citId);
      }
    }
  }

  // Provenance citations referenced in active deliverable
  const stage3ActiveCitations = useMemo<Citation[]>(() => {
    if (!active?.content) return gen?.citations || [];
    const matches = Array.from(active.content.matchAll(/\[\^([^\]]+)\]/g)).map((m) =>
      m[1].replace(/^\^/, "").trim()
    );
    const uniqueIds = Array.from(new Set(matches));
    if (uniqueIds.length === 0) return gen?.citations || [];

    const citMap = new Map<string, Citation>();
    (gen?.citations || []).forEach((c) => citMap.set(c.id.replace(/^\^/, "").trim(), c));

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
  }, [active?.content, gen?.citations]);

  function startNewTransformation() {
    setSessionId(null);
    setGen(null);
    setShowEvidencePanel(false);
    setStage3HighlightedCitationId(null);
    setStage3FocusedOccurrenceIndex(0);
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
    setOriginalEnglishByOutput({});
  }

  function paramsFor(id: OutputTypeId): GenerationParams {
    return paramsByType[id] ?? copyParams(DEFAULT_PARAMS);
  }

  function updateParams(id: OutputTypeId, patch: Partial<GenerationParams>) {
    setParamsByType((prev) => ({
      ...prev,
      [id]: { ...(prev[id] ?? copyParams(DEFAULT_PARAMS)), ...patch },
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

  async function handleScrapeSingleLink(urlToScrape?: string) {
    const targetUrl = (urlToScrape || linkInput).trim();
    if (!targetUrl) return;

    setScrapingError("");
    setScrapingLink(true);

    try {
      const data = await scrapeLink(targetUrl, sessionId || undefined);
      if (data.status === "error") {
        setScrapingError(data.errorMessage || "Failed to scrape link context.");
      }

      setScrapedLinks((prev) => {
        const filtered = prev.filter((item) => item.url.toLowerCase() !== data.url.toLowerCase());
        return [data, ...filtered];
      });

      // Synchronize links string
      setLinks((prev) => {
        const existing = prev.split("\n").map((l) => l.trim()).filter(Boolean);
        if (!existing.includes(data.url)) {
          return [...existing, data.url].join("\n");
        }
        return prev;
      });

      setLinkInput("");
    } catch (err: any) {
      setScrapingError(err?.message || "Error executing link_pipeline on target website.");
    } finally {
      setScrapingLink(false);
    }
  }

  async function handleScrapeAllRawLinks() {
    const rawList = links.split("\n").map((l) => l.trim()).filter(Boolean);
    if (rawList.length === 0) return;

    setScrapingError("");
    setScrapingLink(true);

    try {
      const results: ScrapedLinkData[] = [];
      for (const u of rawList) {
        const d = await scrapeLink(u, sessionId || undefined);
        results.push(d);
      }
      setScrapedLinks(results);
      setLinksInputMode("card");
    } catch (err: any) {
      setScrapingError(err?.message || "Batch link scraping error.");
    } finally {
      setScrapingLink(false);
    }
  }

  function handleRemoveScrapedLink(url: string) {
    setScrapedLinks((prev) => prev.filter((item) => item.url !== url));
    setLinks((prev) => {
      return prev
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l && l !== url)
        .join("\n");
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
      const allDeliverables: Deliverable[] = [];
      const origMap: Partial<Record<OutputTypeId, string>> = {};

      for (const id of selected) {
        const res = await generateDeliverableWithMeta(
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
        const content = res.content;
        const origEn = res.originalEnglish || (paramsFor(id).language === "English" ? content : undefined);
        allDeliverables.push({
          outputType: id,
          content,
          retries: 0,
          originalEnglish: origEn,
        });
        if (origEn) {
          origMap[id] = origEn;
        }
      }

      if (allDeliverables.length === 0) {
        throw new Error("No deliverables could be generated.");
      }

      setOriginalEnglishByOutput((prev) => ({ ...prev, ...origMap }));
      const done: Generation = { ...g, deliverables: allDeliverables, status: "completed" };
      setGen(done);
      if (first) {
        setActiveId(first);
      }

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
      setOriginalEnglishByOutput((prev) => ({ ...prev, [activeId]: content }));
      setGen((prevGen) => {
        if (!prevGen) return prevGen;
        return {
          ...prevGen,
          deliverables: prevGen.deliverables.map((d) =>
            d.outputType === activeId
              ? { ...d, content, originalEnglish: content, retries: d.retries + 1 }
              : d
          ),
        };
      });
      setHistory((prev) => {
        const nextHistory = prev.map((item) => {
          if ((item.sessionId || item.id) === (sessionId || gen?.sessionId || gen?.id)) {
            return {
              ...item,
              deliverables: (item.deliverables || []).map((d) =>
                d.outputType === activeId
                  ? { ...d, content, originalEnglish: content, retries: d.retries + 1 }
                  : d
              ),
            };
          }
          return item;
        });
        localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(nextHistory));
        return nextHistory;
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
      if (item.deliverables) {
        const origMap: Partial<Record<OutputTypeId, string>> = {};
        item.deliverables.forEach((d) => {
          if (d.originalEnglish) {
            origMap[d.outputType] = d.originalEnglish;
          } else if (item.paramsByType?.[d.outputType]?.language === "English") {
            origMap[d.outputType] = d.content;
          }
        });
        setOriginalEnglishByOutput(origMap);
      }
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

  function acceptDraft() {
    if (!gen || !activeId) return;
    const isCurrentlyEnglish = (activeId ? paramsFor(activeId).language : "English") === "English";
    if (isCurrentlyEnglish) {
      setOriginalEnglishByOutput((prev) => ({ ...prev, [activeId]: draft }));
    }
    setGen((prevGen) => {
      if (!prevGen) return prevGen;
      return {
        ...prevGen,
        deliverables: prevGen.deliverables.map((d) =>
          d.outputType === activeId
            ? {
                ...d,
                content: draft,
                originalEnglish: isCurrentlyEnglish ? draft : d.originalEnglish,
              }
            : d
        ),
      };
    });
    setHistory((prev) => {
      const nextHistory = prev.map((item) => {
        if ((item.sessionId || item.id) === (sessionId || gen?.sessionId || gen?.id)) {
          return {
            ...item,
            deliverables: (item.deliverables || []).map((d) =>
              d.outputType === activeId
                ? {
                    ...d,
                    content: draft,
                    originalEnglish: isCurrentlyEnglish ? draft : d.originalEnglish,
                  }
                : d
            ),
          };
        }
        return item;
      });
      localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(nextHistory));
      return nextHistory;
    });
    setEditing(false);
  }

  async function copy() {
    if (!active) return;
    await navigator.clipboard.writeText(active.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function handleSingleDownload(format: "md" | "txt" | "pdf" | "docx") {
    if (!active) return;
    setSingleDownloadOpen(false);
    setExportingFormat(`single-${format}`);
    try {
      await exportDeliverableFile(active.content, active.outputType, format);
    } catch (err) {
      console.error("Single export failed:", err);
      alert(`Failed to export as .${format}. Please try again.`);
    } finally {
      setExportingFormat(null);
    }
  }

  async function handleBatchZipDownload(format: "md" | "txt" | "pdf" | "docx") {
    if (!gen || !gen.deliverables || gen.deliverables.length === 0) return;
    setBatchDownloadOpen(false);
    setExportingFormat(`zip-${format}`);
    try {
      await exportDeliverablesZip(
        gen.deliverables.map((d) => ({ outputType: d.outputType, content: d.content })),
        format,
        sessionId || undefined
      );
    } catch (err) {
      console.error("Batch zip export failed:", err);
      alert(`Failed to package deliverables as .zip (${format}). Please try again.`);
    } finally {
      setExportingFormat(null);
    }
  }

  async function changeDeliverableLanguage(newLang: string) {
    if (!gen || !active || !activeId) return;
    if (paramsFor(activeId).language === newLang) return;

    const originalEnglish = active.originalEnglish || originalEnglishByOutput[activeId];

    setTranslatingLang(true);
    try {
      const translated = await translateDeliverable(
        active.content,
        newLang,
        activeId,
        sessionId || undefined,
        originalEnglish
      );

      updateParams(activeId, { language: newLang });

      const resolvedOriginal = originalEnglish || (newLang === "English" ? translated : undefined);

      setGen((prevGen) => {
        if (!prevGen) return prevGen;
        const updatedDeliverables = prevGen.deliverables.map((d) =>
          d.outputType === activeId
            ? {
                ...d,
                content: translated,
                originalEnglish: d.originalEnglish || resolvedOriginal,
              }
            : d
        );
        return {
          ...prevGen,
          deliverables: updatedDeliverables,
          paramsByType: {
            ...prevGen.paramsByType,
            [activeId]: {
              ...(prevGen.paramsByType?.[activeId] || paramsFor(activeId)),
              language: newLang,
            },
          },
        };
      });

      if (!originalEnglish && newLang === "English") {
        setOriginalEnglishByOutput((prev) => ({ ...prev, [activeId]: translated }));
      }

      setHistory((prev) => {
        const nextHistory = prev.map((item) => {
          if ((item.sessionId || item.id) === (sessionId || gen?.sessionId || gen?.id)) {
            const updatedDeliverables = (item.deliverables || []).map((d) =>
              d.outputType === activeId
                ? {
                    ...d,
                    content: translated,
                    originalEnglish: d.originalEnglish || resolvedOriginal,
                  }
                : d
            );
            return {
              ...item,
              deliverables: updatedDeliverables,
              paramsByType: {
                ...item.paramsByType,
                [activeId]: {
                  ...(item.paramsByType?.[activeId] || paramsFor(activeId)),
                  language: newLang,
                },
              },
            };
          }
          return item;
        });
        localStorage.setItem(getAccountHistoryKey(user?.email), JSON.stringify(nextHistory));
        return nextHistory;
      });
    } catch (err) {
      console.error("Language translation failed:", err);
      alert(`Could not translate deliverable to ${newLang}. Please try again.`);
    } finally {
      setTranslatingLang(false);
    }
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
            {sourceTab === "links" && (
              <div className="link-pipeline-box">
                <div className="link-mode-toggle">
                  <button onClick={() => setLinksInputMode((m) => (m === "card" ? "raw" : "card"))}>
                    {linksInputMode === "card" ? "Switch to Bulk Raw URLs" : "Switch to Link Card Inspector"}
                  </button>
                </div>

                {linksInputMode === "card" ? (
                  <>
                    <div className="link-input-row">
                      <input
                        type="url"
                        placeholder="https://news.example.com/cyber-threat-report"
                        value={linkInput}
                        onChange={(e) => setLinkInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !scrapingLink) {
                            e.preventDefault();
                            handleScrapeSingleLink();
                          }
                        }}
                        disabled={scrapingLink}
                      />
                      <button
                        className="primary sm"
                        onClick={() => handleScrapeSingleLink()}
                        disabled={scrapingLink || !linkInput.trim()}
                      >
                        {scrapingLink ? "Scraping..." : "Scrape & Extract Context"}
                      </button>
                    </div>

                    {scrapingLink && (
                      <div className="scraping-banner">
                        <div className="scraping-spinner" />
                        <span>
                          <strong>link_pipeline active:</strong> Scraping website, removing boilerplate, extracting metadata & IOCs...
                        </span>
                      </div>
                    )}

                    {scrapingError && (
                      <div className="alert danger sm" style={{ margin: "4px 0" }}>
                        {scrapingError}
                      </div>
                    )}

                    {scrapedLinks.length === 0 && !scrapingLink && (
                      <p className="muted" style={{ fontSize: "12px", marginTop: "4px" }}>
                        Provide public threat advisories, blog posts, news articles, or bulletin URLs. The <code>link_pipeline</code> will automatically scrape content, extract IOCs, and generate normalized <code>.md</code> and <code>.json</code> metadata files.
                      </p>
                    )}

                    {scrapedLinks.length > 0 && (
                      <div className="scraped-cards-list">
                        {scrapedLinks.map((item) => {
                          const cveCount = item.iocs?.cves?.length || 0;
                          const ipCount = item.iocs?.ipv4_addresses?.length || 0;
                          const actorCount = item.iocs?.threat_actors?.length || 0;

                          return (
                            <div key={item.url} className="scraped-card">
                              <div className="scraped-card-header">
                                <div className="scraped-card-title-group">
                                  <span className="scraped-domain-badge">
                                    🌐 {item.domain || "Web Source"}
                                  </span>
                                  <div className="scraped-card-title" title={item.title}>
                                    {item.title}
                                  </div>
                                  <div className="scraped-card-meta-line">
                                    {item.author ? `By ${item.author} · ` : ""}
                                    {item.published_time ? `Published ${item.published_time.slice(0, 10)} · ` : ""}
                                    <a href={item.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>
                                      Visit Source ↗
                                    </a>
                                  </div>
                                </div>
                                <button
                                  className="scraped-btn-remove"
                                  title="Remove link"
                                  onClick={() => handleRemoveScrapedLink(item.url)}
                                >
                                  ×
                                </button>
                              </div>

                              {item.description && (
                                <div className="scraped-card-desc">{item.description}</div>
                              )}

                              <div className="scraped-card-tags">
                                <span className="scraped-tag-stat">
                                  📝 {item.word_count?.toLocaleString() || 0} words
                                </span>
                                {cveCount > 0 && (
                                  <span className="scraped-tag-cve">
                                    {cveCount} CVE{cveCount > 1 ? "s" : ""}: {item.iocs.cves?.slice(0, 2).join(", ")}
                                  </span>
                                )}
                                {ipCount > 0 && (
                                  <span className="scraped-tag-ip">
                                    {ipCount} IP{ipCount > 1 ? "s" : ""}
                                  </span>
                                )}
                                {actorCount > 0 && (
                                  <span className="scraped-tag-actor">
                                    Adversary: {item.iocs.threat_actors?.slice(0, 1).join(", ")}
                                  </span>
                                )}
                              </div>

                              <div className="scraped-card-actions">
                                <button
                                  className="scraped-btn-action"
                                  onClick={() =>
                                    setViewingArtifact({
                                      type: "md",
                                      title: item.title,
                                      filename: item.md_filename || `${item.domain}_context.md`,
                                      content: item.markdown,
                                    })
                                  }
                                >
                                  📄 View .md Context
                                </button>
                                <button
                                  className="scraped-btn-action"
                                  onClick={() =>
                                    setViewingArtifact({
                                      type: "json",
                                      title: item.title,
                                      filename: item.json_filename || `${item.domain}_metadata.json`,
                                      content: JSON.stringify(item.metadata, null, 2),
                                    })
                                  }
                                >
                                  📋 View .json Metadata
                                </button>
                                <button
                                  className="scraped-btn-action"
                                  onClick={() =>
                                    triggerFileDownload(
                                      item.markdown,
                                      item.md_filename || `${item.domain}_context.md`,
                                      "text/markdown"
                                    )
                                  }
                                >
                                  ⬇️ .md
                                </button>
                                <button
                                  className="scraped-btn-action"
                                  onClick={() =>
                                    triggerFileDownload(
                                      JSON.stringify(item.metadata, null, 2),
                                      item.json_filename || `${item.domain}_metadata.json`,
                                      "application/json"
                                    )
                                  }
                                >
                                  ⬇️ .json
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <textarea
                      className="source-text"
                      placeholder={"https://example.org/threat-report\nhttps://news.example.com/breach"}
                      value={links}
                      onChange={(e) => setLinks(e.target.value)}
                      rows={6}
                    />
                    <button
                      className="ghost sm"
                      style={{ alignSelf: "flex-start", marginTop: "6px" }}
                      onClick={handleScrapeAllRawLinks}
                      disabled={scrapingLink || !links.trim()}
                    >
                      {scrapingLink ? "Scraping all links..." : "⚡ Scrape All Links via link_pipeline"}
                    </button>
                  </>
                )}
              </div>
            )}
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
                <div className="deliverables-header-actions">
                  <button
                    type="button"
                    className={`ghost sm evidence-toggle-btn ${showEvidencePanel ? "on active" : ""}`}
                    onClick={() => setShowEvidencePanel(!showEvidencePanel)}
                    title="Toggle Source Evidence Grounding Inspector"
                  >
                    {showEvidencePanel ? "✕ Close Evidence" : `🔍 Source Evidence (${stage3EvidenceItems.length})`}
                  </button>
                  <div className="download-dropdown-wrapper" ref={batchDropdownRef}>
                    <button
                      className="ghost sm download-btn batch-download-btn"
                      onClick={() => setBatchDownloadOpen(!batchDownloadOpen)}
                      disabled={!!exportingFormat || !gen?.deliverables?.length}
                      title="Download all deliverables at once in a .zip archive"
                    >
                      {exportingFormat && exportingFormat.startsWith("zip-") ? (
                        <span>Packaging {exportingFormat.replace("zip-", "").toUpperCase()}…</span>
                      ) : (
                        <>
                          <span>📦 Download All (.zip)</span>
                          <span className="dropdown-caret">▾</span>
                        </>
                      )}
                    </button>
                    {batchDownloadOpen && (
                      <div className="download-dropdown-menu batch-menu">
                        <div className="download-menu-header">Download All Deliverables as:</div>
                        <button onClick={() => handleBatchZipDownload("md")} className="download-menu-item">
                          <span className="format-icon">📄</span>
                          <span className="format-title">All as Markdown</span>
                          <span className="format-ext">.md in .zip</span>
                        </button>
                        <button onClick={() => handleBatchZipDownload("txt")} className="download-menu-item">
                          <span className="format-icon">📝</span>
                          <span className="format-title">All as Plain Text</span>
                          <span className="format-ext">.txt in .zip</span>
                        </button>
                        <button onClick={() => handleBatchZipDownload("pdf")} className="download-menu-item">
                          <span className="format-icon">📕</span>
                          <span className="format-title">All as PDF Documents</span>
                          <span className="format-ext">.pdf in .zip</span>
                        </button>
                        <button onClick={() => handleBatchZipDownload("docx")} className="download-menu-item">
                          <span className="format-icon">📘</span>
                          <span className="format-title">All as Word Documents</span>
                          <span className="format-ext">.docx in .zip</span>
                        </button>
                      </div>
                    )}
                  </div>
                  <button
                    className="ghost sm"
                    onClick={startNewTransformation}
                  >
                    + New transformation
                  </button>
                </div>
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
                <div className={`deliverables-split-layout ${showEvidencePanel ? "has-evidence-sidebar" : ""}`}>
                  {showEvidencePanel && (
                    <aside className="deliverables-evidence-sidebar">
                      <div className="sidebar-header-row">
                        <div className="sidebar-title-group">
                          <span className="sidebar-title">Source Evidence Grounding</span>
                          <span className="source-count-pill">{stage3EvidenceItems.length} items</span>
                        </div>
                        <button
                          type="button"
                          className="ghost sm close-sidebar-btn"
                          onClick={() => setShowEvidencePanel(false)}
                          title="Collapse Source Evidence Panel"
                        >
                          ✕
                        </button>
                      </div>
                      <SourceEvidenceInspector
                        evidenceItems={stage3EvidenceItems}
                        visualEvidenceItems={stage3VisualEvidenceItems}
                        activeVisualEvidence={stage3ActiveVisual || (stage3VisualEvidenceItems[0] ?? null)}
                        highlightedCitationId={stage3HighlightedCitationId}
                        sourceViewMode={stage3SourceViewMode}
                        groundingMd={gen?.groundingMd || groundingMd || ""}
                        sourceText={gen?.sourceText || sourceText || ""}
                        filterQuery={stage3FilterQuery}
                        activeDraftText={active?.content || ""}
                        onFilterChange={setStage3FilterQuery}
                        onViewModeChange={setStage3SourceViewMode}
                        onSelectVisualEvidence={setStage3ActiveVisual}
                        onSelectEvidence={handleStage3SelectEvidence}
                      />
                    </aside>
                  )}

                  <div className="deliverable-main-content">
                    <div className="card deliverable">
                      <div className="deliverable-toolbar">
                        {editing ? (
                          <>
                            <button className="ghost sm" onClick={() => setEditing(false)}>Discard</button>
                            <button className="primary sm" onClick={acceptDraft}>Save changes</button>
                          </>
                        ) : (
                          <>
                            <div className="deliverable-lang-picker">
                              <span className="lang-picker-icon">🌐</span>
                              <select
                                className="lang-picker-select"
                                value={activeId ? paramsFor(activeId).language : "English"}
                                onChange={(e) => changeDeliverableLanguage(e.target.value)}
                                disabled={translatingLang || generating}
                                title="Update deliverable language (English, Hindi, Telugu)"
                              >
                                {LANGUAGES.map((l) => (
                                  <option key={l} value={l}>
                                    {l}
                                  </option>
                                ))}
                              </select>
                              {translatingLang && <span className="lang-translating-spinner">Translating…</span>}
                            </div>
                            <button className="ghost sm" onClick={() => { setDraft(active.content); setEditing(true); }}>Edit markdown</button>
                            <button className="ghost sm" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
                            <div className="download-dropdown-wrapper" ref={singleDropdownRef}>
                              <button
                                className="ghost sm download-btn"
                                onClick={() => setSingleDownloadOpen(!singleDownloadOpen)}
                                disabled={!!exportingFormat}
                              >
                                {exportingFormat && exportingFormat.startsWith("single-") ? (
                                  <span>Downloading {exportingFormat.replace("single-", "").toUpperCase()}…</span>
                                ) : (
                                  <>
                                    <span>⬇️ Download</span>
                                    <span className="dropdown-caret">▾</span>
                                  </>
                                )}
                              </button>
                              {singleDownloadOpen && (
                                <div className="download-dropdown-menu">
                                  <div className="download-menu-header">Select Format:</div>
                                  <button onClick={() => handleSingleDownload("md")} className="download-menu-item">
                                    <span className="format-icon">📄</span>
                                    <span className="format-title">Markdown</span>
                                    <span className="format-ext">.md</span>
                                  </button>
                                  <button onClick={() => handleSingleDownload("txt")} className="download-menu-item">
                                    <span className="format-icon">📝</span>
                                    <span className="format-title">Plain Text</span>
                                    <span className="format-ext">.txt</span>
                                  </button>
                                  <button onClick={() => handleSingleDownload("pdf")} className="download-menu-item">
                                    <span className="format-icon">📕</span>
                                    <span className="format-title">PDF Document</span>
                                    <span className="format-ext">.pdf</span>
                                  </button>
                                  <button onClick={() => handleSingleDownload("docx")} className="download-menu-item">
                                    <span className="format-icon">📘</span>
                                    <span className="format-title">Word Document</span>
                                    <span className="format-ext">.docx</span>
                                  </button>
                                </div>
                              )}
                            </div>
                          </>
                        )}
                      </div>

                      {/* Bidirectional Occurrence Navigation Bar */}
                      {!editing && stage3HighlightedCitationId && (
                        <div className="bidirectional-nav-bar">
                          <div className="nav-bar-info">
                            <span className="nav-bar-badge">[^{stage3HighlightedCitationId}]</span>
                            <span className="nav-bar-label">
                              {stage3TotalOccurrences > 1
                                ? `Referenced in ${stage3TotalOccurrences} places · Claim ${stage3FocusedOccurrenceIndex + 1} of ${stage3TotalOccurrences}`
                                : stage3TotalOccurrences === 1
                                ? "Referenced in 1 claim sentence"
                                : "Active Evidence Citation"}
                            </span>
                          </div>
                          <div className="nav-bar-actions">
                            {stage3TotalOccurrences > 1 && (
                              <>
                                <button
                                  type="button"
                                  className="ghost sm nav-cycle-btn"
                                  onClick={handleStage3PrevOccurrence}
                                  title="Jump to previous referencing claim"
                                >
                                  ◀ Prev
                                </button>
                                <button
                                  type="button"
                                  className="ghost sm nav-cycle-btn"
                                  onClick={handleStage3NextOccurrence}
                                  title="Jump to next referencing claim"
                                >
                                  Next ▶
                                </button>
                              </>
                            )}
                            <button
                              type="button"
                              className="ghost sm nav-clear-btn"
                              onClick={handleStage3ClearCitation}
                              title="Clear citation highlight"
                            >
                              ✕ Clear
                            </button>
                          </div>
                        </div>
                      )}

                      {editing ? (
                        <textarea className="md-editor" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
                      ) : (
                        <div
                          className="preview-rendered-pane interactive-pane deliverable-rendered-pane"
                          ref={deliverableContentRef}
                          onClick={handleStage3DeliverableClick}
                        >
                          <Markdown content={stage3AnnotatedContent} />
                        </div>
                      )}

                      {/* Citations provenance tray */}
                      {!editing && stage3ActiveCitations.length > 0 && (
                        <div className="citation-box provenance-citation-box">
                          <div className="citation-box-header">
                            <strong>Provenance Anchors ({stage3ActiveCitations.length})</strong>
                            <span className="muted">Click any citation pill to inspect its source evidence chunk</span>
                          </div>
                          <div className="citation-list">
                            {stage3ActiveCitations.map((citation) => (
                              <button
                                key={citation.id}
                                type="button"
                                className={`citation-chip interactive-chip ${
                                  stage3HighlightedCitationId?.toLowerCase() === citation.id.toLowerCase() ? "active" : ""
                                }`}
                                onClick={() => scrollToStage3Source(citation.id)}
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
                      )}
                    </div>
                  </div>
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

      {viewingArtifact && (
        <div
          className="artifact-modal-overlay"
          onClick={() => setViewingArtifact(null)}
        >
          <div
            className="artifact-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="artifact-modal-header">
              <div className="artifact-modal-title">
                <span>{viewingArtifact.type === "md" ? "📄 Context Markdown" : "📋 Metadata JSON"}</span>
                <span className="muted" style={{ fontSize: "12px", fontFamily: "var(--mono)" }}>
                  ({viewingArtifact.filename})
                </span>
              </div>
              <div className="artifact-modal-controls">
                <button
                  className="ghost sm"
                  onClick={() => {
                    navigator.clipboard.writeText(viewingArtifact.content);
                    setCopiedArtifact(true);
                    setTimeout(() => setCopiedArtifact(false), 2000);
                  }}
                >
                  {copiedArtifact ? "✓ Copied!" : "Copy"}
                </button>
                <button
                  className="ghost sm"
                  onClick={() =>
                    triggerFileDownload(
                      viewingArtifact.content,
                      viewingArtifact.filename,
                      viewingArtifact.type === "md" ? "text/markdown" : "application/json"
                    )
                  }
                >
                  ⬇️ Download
                </button>
                <button
                  className="ghost sm"
                  onClick={() => setViewingArtifact(null)}
                >
                  ✕ Close
                </button>
              </div>
            </div>
            <div className="artifact-modal-body">
              <pre className="artifact-modal-code">
                <code>{viewingArtifact.content}</code>
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

