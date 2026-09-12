# Transmute Platform — Architectural & Structural Changes Documentation

**Date:** September 13, 2026  
**System:** Transmute Multimodal Threat Intelligence & Content Synthesis Platform  
**Target Repository:** `/home/saksham/sih_merge_enhance`

---

## 1. Executive Overview

This document provides a complete technical breakdown of the structural, backend, and frontend architectural enhancements implemented across the **Transmute** platform.

The primary goals accomplished:
1. **Re-established 100% multimodal grounding:** Eradicated synthetic fallback hallucinations (`BankShield`, `ShadowGate Collective`) and context truncation.
2. **Interactive inline sensitivity workflow:** Replaced raw HTML and destructive regex replacements with deterministic character-offset tracking and an operator decision popover (Redact, Accept, Delete).
3. **Dual-Pane Source-to-Draft Provenance Viewer:** Built an interactive split-screen workspace with 1:1 citation highlighting and draft-synchronized provenance trays.
4. **End-to-end integration of the 4 core enhancements:** Deterministic Sensitivity Checker, NLI Cross-Encoder Guardrail, Citation Re-Linker, and Readability / Tone Scorer.
5. **Fixed premature media truncation:** Restored full scene extraction on audio/video ingestion streams.
6. **Eliminated deliverable redaction leakage:** Cleaned up review wrappers (`[SENSITIVE: ...]`, double-wrapped tags) ensuring pristine deliverable outputs.

---

## 2. Directory & Module Structural Changes

```
sih_merge_enhance/
├── backend/
│   ├── main.py                     # App factory, lifespan, CORS, and router registration
│   ├── config.py                   # Environment settings (ports, API keys, storage paths)
│   ├── database.py                 # SQLite metadata persistence
│   ├── routers/
│   │   ├── health.py               # System & model connectivity health checks
│   │   ├── auth.py                 # Authentication and session management
│   │   ├── pipeline.py             # Plan generation, deliverable synthesis, file ingestion
│   │   ├── proofcheck.py           # Dedicated non-destructive sensitivity scanning endpoint
│   │   └── chat.py                 # Grounded threat intelligence chat assistant
│   └── services/
│       ├── conditional_service.py  # Orchestrator integrating all 4 enhancements into pipeline
│       ├── preview_service.py      # Multi-platform preview draft generation coordinator
│       └── deliverable_service.py  # Final deliverable synthesis with guardrail verification
│
├── preview_pipeline/
│   ├── generator.py                # LLM synthesis engine for multi-format previews
│   ├── mock.py                     # Dynamic grounded mock generator (no synthetic fallbacks)
│   ├── proofchecker.py             # Sensitivity and citation proofchecker bridge
│   └── types.py                    # Pydantic data models for previews and flags
│
├── final_post_pipeline/
│   ├── generator.py                # Final deliverable LLM synthesis & strip_preview_wrappers()
│   ├── mock.py                     # Deterministic approved-draft fallback generator
│   └── category_prompts.py         # Specialized prompt templates per deliverable category
│
├── enhancements/
│   ├── sensitivity_checker/        # Enhancement 1: Deterministic Aho-Corasick + Shannon entropy scanner
│   ├── nli_guardrail/              # Enhancement 2: Cross-encoder factual verification of citations
│   ├── anchor_relinker/            # Enhancement 3: Citation re-anchoring when drafts are edited
│   └── readability_scorer/         # Enhancement 4: Platform-specific Flesch/Kincaid & Fog scoring
│
├── frontend/src/
│   ├── components/
│   │   ├── ReviewWorkspace.tsx     # [NEW] Dual-pane split viewer (Source Evidence + Draft Preview)
│   │   ├── InteractivePreviewEditor.tsx # [NEW] Inline red badge rendering & operator decision popover
│   │   └── ...
│   ├── pages/
│   │   └── Dashboard.tsx           # Main application view seamlessly switching to ReviewWorkspace
│   └── lib/
│       ├── mock.ts                 # Dynamic client-side entity extraction & deliverable fallback
│       └── types.ts                # TypeScript definitions for SensitiveDataFlag, Citation, etc.
│
└── tests/
    ├── test_strip_preview_wrappers.py       # Validates preview badge stripping & leak prevention
    ├── test_interactive_sensitivity.py      # Verifies non-destructive offsets & zero text corruption
    ├── test_proofchecker_deterministic.py   # Sub-10ms RFC1918 & wordlist automaton test suite
    └── test_backend_e2e.py                  # Full pipeline API integration tests
```

---

## 3. Detailed Structural Enhancements

### 3.1. Restoring Multimodal Grounding & Removing Canned Hallucinations

* **Problem Solved:** When API keys were unset, or when input was processed, earlier code dropped context and fell back to a hardcoded banking breach mock scenario (`BankShield`, `ShadowGate Collective`, `CVE-2026-41822`).
* **Implementation:**
  * **Dynamic Grounded Mock Generator (`preview_pipeline/mock.py`):**
    Added `build_grounded_mock_dict(content_md)` which dynamically parses real threat actors (e.g., Conti, REvil, LockBit, Sophos Rapid Response, IBM X-Force, CERT-In, NIST), CVE identifiers, IPs, and telemetry facts from the ingested source. The canned `BankShield` scenario is restricted strictly to when source input is completely empty.
  * **Unrestricted Multimodal Context (`preview_pipeline/generator.py` & `final_post_pipeline/generator.py`):**
    Removed `content_md[:4000]` and `content_md[:3500]` slices. All ingested OCR image extractions (`1.png`–`9.png`), PDF analyses, and audio transcripts are provided in full to the LLM context window.
  * **Rate Limit Hardening:**
    Configured Groq `max_tokens=950` to stay strictly within Groq free-tier 1,000 OTPM limits and added `gemini-3.6-flash` and `gemini-3.5-flash-lite` to candidate models.

---

### 3.2. Interactive Inline Sensitivity Flagging (Zero Text Corruption)

* **Problem Solved:** Sensitive items either dumped clumsy raw HTML tags or erased tokens into empty whitespace (`achieved access via .`) before operator review.
* **Implementation:**
  * **Deterministic Backend Scanning (`enhancements/sensitivity_checker/scanner.py`):**
    The backend scanner preserves draft markdown 100% intact, returning structured metadata:
    `[{"flag_id": "flag-1", "entity_type": "INTERNAL_IP", "char_start": 283, "char_end": 295, "severity": "CRITICAL", "matched_text": "192.168.50.4", "suggested_action": "REDACT"}]`.
  * **Non-Destructive Frontend Annotation (`frontend/src/components/InteractivePreviewEditor.tsx`):**
    The raw draft text stored in application state remains clean markdown. During display, `annotatedMarkdown` wraps flagged spans with interactive `.sensitive-flag.sensitive-flag-badge` elements.
  * **Operator Decision Workflow:**
    Clicking any flagged badge opens a floating decision popover with three clear options:
    1. **Redact:** Replaces the token with `[REDACTED: ENTITY_TYPE]` or custom mask, updating subsequent character offsets.
    2. **Accept:** Dismisses the flag and retains the original sensitive text.
    3. **Delete:** Strips the sensitive text completely without leaving trailing spaces.
  * **Offset Drift Protection:**
    `redactFlag`, `deleteFlag`, and `redactAll` verify character slices against `flag.matched_text` before slicing, preventing offset drift or corrupted tokens.

---

### 3.3. Dual-Pane Source-to-Draft Provenance Viewer

* **Problem Solved:** Operators reviewing drafts could not easily cross-reference claims and citations against original source evidence.
* **Implementation:**
  * **Layout (`frontend/src/components/ReviewWorkspace.tsx`):**
    Implements a responsive split-screen review stage:
    * **Left Pane (Source Evidence Inspector):** Renders structured cards for OCR extractions, PDF segments, audio/video timestamps, and raw telemetry with quick search filtering.
    * **Right Pane (Draft Preview & Proofchecker):** Contains the interactive preview editor, platform tab toggles, readability badges, and the provenance tray.
  * **1:1 Citation Synchronization:**
    `activeDraftCitations` scans the active draft for citation markers (`[^src-1]`, `[^img-2]`, `[^aud-1]`) and updates the **Provenance Anchors** tray in real time.
  * **Click-to-Scroll & Visual Pulse:**
    Clicking an inline citation pill or provenance chip triggers `scrollToSource()`, smoothly scrolling the left evidence pane directly to the originating evidence card and applying a temporary amber highlight pulse.

---

### 3.4. Deliverable Redaction Leak Prevention

* **Problem Solved:** Review tags (`[SENSITIVE: ...]`, `.sensitive-flag-badge` spans) and double-wrapped tokens (`[SENSITIVE: [REDACTED: INTERNAL_IP]]`) were leaking into the final deliverable phase.
* **Implementation:**
  * **`strip_preview_wrappers()` in `final_post_pipeline/generator.py`:**
    * Unpacks double-wrapped tags: `[SENSITIVE: [REDACTED: IP]]` -> `[REDACTED: IP]`.
    * Strips interactive review badges: `<span class="sensitive-flag-badge ...">...</span>` -> plain text.
    * Preserves operator-redacted tokens: `[REDACTED: INTERNAL_IP]` and `[RESTRICTED]`.
    * Protects classification metadata: `**CLASSIFICATION:** STRICTLY CONFIDENTIAL // BOARD MATERIAL` remains untouched.
  * **Clean Fallback Synthesis (`final_post_pipeline/mock.py`):**
    Returns the operator's approved draft cleanly without synthetic disclaimers.

---

### 3.5. Verification & Active Enhancements Execution

The final post pipeline executes all 4 enhancements during deliverable finalization:
1. **Citation Re-Linker:** If an operator edits draft text, `relink_citations()` recalculates sentence positions and ensures citation markers remain attached to their originating claims.
2. **NLI Guardrail:** `verify_citations()` executes cross-encoder natural language inference to evaluate whether cited sentences entail, contradict, or remain neutral relative to the source context.
3. **Readability Scorer:** `score_readability()` scores Flesch Reading Ease, Flesch-Kincaid Grade Level, and Gunning Fog index against the target platform's audience profile (Executive Brief vs. SOC Advisory vs. LinkedIn Post).

---

## 4. How to Run and Verify the System

### 4.1. Start the Backend Server (Port 8000)
```bash
cd /home/saksham/sih_merge_enhance
/home/saksham/sih_enhancements/.venv/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2. Start the Frontend Server (Port 5173)
```bash
cd /home/saksham/sih_merge_enhance/frontend
npm run dev
```

### 4.3. Run Automated Verification Tests
```bash
cd /home/saksham/sih_merge_enhance

# 1. Verify leak prevention and wrapper stripping
/home/saksham/sih_enhancements/.venv/bin/python3 tests/test_strip_preview_wrappers.py

# 2. Verify interactive sensitivity offsets and zero text corruption
/home/saksham/sih_enhancements/.venv/bin/python3 tests/test_interactive_sensitivity.py

# 3. Verify deterministic proofchecker speed and Aho-Corasick automaton
/home/saksham/sih_enhancements/.venv/bin/python3 tests/test_proofchecker_deterministic.py

# 4. Verify frontend build
npm --prefix frontend run build
```
