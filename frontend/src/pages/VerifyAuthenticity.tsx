import React, { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyDeliverableApi, getRegistryEntryApi } from "../lib/mock";

type VerifyTab = "upload" | "paste" | "registry";

export default function VerifyAuthenticity() {
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<VerifyTab>("upload");

  // File Upload State
  const [docFile, setDocFile] = useState<File | null>(null);
  const [sigFile, setSigFile] = useState<File | null>(null);

  // Paste State
  const [contentPaste, setContentPaste] = useState("");
  const [signaturePaste, setSignaturePaste] = useState("");
  const [keyIdPaste, setKeyIdPaste] = useState("");

  // Registry Lookup State
  const [registryQuery, setRegistryQuery] = useState("");

  // Result & Loading
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Auto-verify if URL parameters are provided (e.g. from scanning a QR code)
  useEffect(() => {
    const idParam = searchParams.get("id");
    const hashParam = searchParams.get("hash");
    if (hashParam || idParam) {
      setTab("registry");
      setRegistryQuery(hashParam || idParam || "");
      handleAutoRegistryVerify(hashParam || idParam || "");
    }
  }, [searchParams]);

  async function handleAutoRegistryVerify(query: string) {
    setVerifying(true);
    setError(null);
    setResult(null);
    try {
      const res = await verifyDeliverableApi({
        content_hash: query.length === 64 ? query : undefined,
        deliverable_id: query.length !== 64 ? query : undefined,
      });
      setResult(res);
    } catch (err: any) {
      setError(err?.message || "Failed to verify query against public registry.");
    } finally {
      setVerifying(false);
    }
  }

  async function handleVerifySubmit(e: React.FormEvent) {
    e.preventDefault();
    setVerifying(true);
    setError(null);
    setResult(null);

    try {
      if (tab === "upload") {
        if (!docFile) {
          throw new Error("Please select a deliverable file to verify.");
        }
        const res = await verifyDeliverableApi({
          file: docFile,
          sig_file: sigFile || undefined,
        });
        setResult(res);
      } else if (tab === "paste") {
        if (!contentPaste.trim()) {
          throw new Error("Please enter or paste the deliverable content.");
        }
        if (!signaturePaste.trim()) {
          throw new Error("Please enter the Ed25519 digital signature string.");
        }
        const res = await verifyDeliverableApi({
          content: contentPaste,
          signature: signaturePaste.trim(),
          signing_key_id: keyIdPaste.trim() || undefined,
        });
        setResult(res);
      } else if (tab === "registry") {
        if (!registryQuery.trim()) {
          throw new Error("Please enter a SHA-256 hash or Deliverable UUID.");
        }
        const query = registryQuery.trim();
        const res = await verifyDeliverableApi({
          content_hash: query.length === 64 ? query : undefined,
          deliverable_id: query.length !== 64 ? query : undefined,
        });
        setResult(res);
      }
    } catch (err: any) {
      setError(err?.message || "An error occurred during verification.");
    } finally {
      setVerifying(false);
    }
  }

  function resetForm() {
    setDocFile(null);
    setSigFile(null);
    setContentPaste("");
    setSignaturePaste("");
    setKeyIdPaste("");
    setRegistryQuery("");
    setResult(null);
    setError(null);
  }

  return (
    <div className="verify-page-container">
      {/* Header */}
      <header className="verify-header">
        <div className="verify-brand">
          <Link to="/" className="brand-logo-link">
            <span className="verify-brand-icon">🛡️</span>
            <span className="verify-brand-title">TRANSMUTE</span>
          </Link>
          <span className="verify-divider">/</span>
          <span className="verify-page-label">Cryptographic Authenticity & Watermark Verifier</span>
        </div>
        <Link to="/" className="ghost sm verify-back-btn">
          ← Back to Workspace
        </Link>
      </header>

      {/* Hero */}
      <main className="verify-main">
        <div className="verify-hero">
          <div className="verify-shield-badge">ED25519 NOTARY SEAL</div>
          <h1 className="verify-hero-title">Verify Threat Advisory Authenticity</h1>
          <p className="verify-hero-subtitle">
            Validate digital provenance, detect tampering, and confirm unforgeable cryptographic seals
            issued by Transmute Threat Intelligence CERT across supply chains.
          </p>
        </div>

        {/* Verification Card */}
        <div className="card verify-card">
          <div className="verify-tabs" role="tablist">
            <button
              type="button"
              className={`verify-tab-btn ${tab === "upload" ? "active" : ""}`}
              onClick={() => { setTab("upload"); setResult(null); setError(null); }}
            >
              📄 Upload File + .sig
            </button>
            <button
              type="button"
              className={`verify-tab-btn ${tab === "paste" ? "active" : ""}`}
              onClick={() => { setTab("paste"); setResult(null); setError(null); }}
            >
              ✍️ Paste Content & Signature
            </button>
            <button
              type="button"
              className={`verify-tab-btn ${tab === "registry" ? "active" : ""}`}
              onClick={() => { setTab("registry"); setResult(null); setError(null); }}
            >
              🔍 Public Registry Lookup
            </button>
          </div>

          <form onSubmit={handleVerifySubmit} className="verify-form">
            {tab === "upload" && (
              <div className="verify-upload-section">
                <div className="file-dropzone">
                  <label className="dropzone-label">
                    <span className="dropzone-icon">📥</span>
                    <strong>Deliverable Document</strong>
                    <span className="muted">Upload .md, .txt, or .pdf advisory</span>
                    <input
                      type="file"
                      onChange={(e) => setDocFile(e.target.files?.[0] || null)}
                      className="file-input-hidden"
                    />
                  </label>
                  {docFile && (
                    <div className="file-selected-tag">
                      ✓ {docFile.name} ({(docFile.size / 1024).toFixed(1)} KB)
                    </div>
                  )}
                </div>

                <div className="file-dropzone">
                  <label className="dropzone-label">
                    <span className="dropzone-icon">🔏</span>
                    <strong>Detached Sidecar (.sig)</strong>
                    <span className="muted">Optional if verifying standalone document</span>
                    <input
                      type="file"
                      accept=".sig,.json"
                      onChange={(e) => setSigFile(e.target.files?.[0] || null)}
                      className="file-input-hidden"
                    />
                  </label>
                  {sigFile && (
                    <div className="file-selected-tag">
                      ✓ {sigFile.name} ({(sigFile.size / 1024).toFixed(1)} KB)
                    </div>
                  )}
                </div>
              </div>
            )}

            {tab === "paste" && (
              <div className="verify-paste-section">
                <div className="form-group">
                  <label>Deliverable Markdown / Text Content:</label>
                  <textarea
                    rows={6}
                    placeholder="Paste the full deliverable content text here..."
                    value={contentPaste}
                    onChange={(e) => setContentPaste(e.target.value)}
                    className="verify-textarea"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group flex-2">
                    <label>Base64 Ed25519 Signature:</label>
                    <input
                      type="text"
                      placeholder="e.g. Y7e1q8x9...=="
                      value={signaturePaste}
                      onChange={(e) => setSignaturePaste(e.target.value)}
                      className="verify-input"
                    />
                  </div>
                  <div className="form-group flex-1">
                    <label>Signing Key ID (Optional):</label>
                    <input
                      type="text"
                      placeholder="e.g. transmute-key-2026-v1"
                      value={keyIdPaste}
                      onChange={(e) => setKeyIdPaste(e.target.value)}
                      className="verify-input"
                    />
                  </div>
                </div>
              </div>
            )}

            {tab === "registry" && (
              <div className="verify-registry-section">
                <div className="form-group">
                  <label>SHA-256 Digest or Deliverable UUID:</label>
                  <input
                    type="text"
                    placeholder="Enter 64-character SHA-256 hash or deliverable UUID..."
                    value={registryQuery}
                    onChange={(e) => setRegistryQuery(e.target.value)}
                    className="verify-input"
                  />
                  <span className="input-hint muted">
                    Validates whether this deliverable fingerprint was officially registered by Transmute CERT without exposing document contents.
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="verify-error-banner">
                ⚠️ {error}
              </div>
            )}

            <div className="verify-actions">
              <button type="button" className="ghost sm" onClick={resetForm} disabled={verifying}>
                Reset
              </button>
              <button type="submit" className="primary" disabled={verifying}>
                {verifying ? "Cryptographic Proof Checking…" : "Verify Authenticity & Integrity"}
              </button>
            </div>
          </form>
        </div>

        {/* Dynamic Live Result Card */}
        {result && (
          <div className={`card verify-result-card ${result.valid ? "result-valid" : "result-invalid"}`}>
            <div className="result-header">
              <div className="result-icon-large">
                {result.valid ? "🛡️" : result.status === "NOT_FOUND" ? "❓" : "🚨"}
              </div>
              <div className="result-title-group">
                <div className="result-status-pill">
                  {result.valid ? "AUTHENTIC & VERIFIED" : result.status || "VERIFICATION FAILED"}
                </div>
                <h2>
                  {result.valid
                    ? "Cryptographic Seal Valid — Content Is Pristine"
                    : result.status === "NOT_FOUND"
                    ? "Deliverable Fingerprint Not Registered"
                    : "Tampering or Forgery Detected"}
                </h2>
              </div>
            </div>

            <p className="result-summary-text">
              {result.details}
            </p>

            <div className="result-details-grid">
              <div className="detail-item">
                <span className="detail-label">Originating Authority</span>
                <strong className="detail-value">{result.organization || "Transmute Threat Intel CERT"}</strong>
              </div>
              <div className="detail-item">
                <span className="detail-label">Classification / TLP</span>
                <span className="tlp-badge amber">{result.tlp_level || "TLP:AMBER+STRICT"}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Signing Algorithm</span>
                <strong className="detail-value">Ed25519 (Asymmetric 256-bit)</strong>
              </div>
              <div className="detail-item">
                <span className="detail-label">Signer Key ID</span>
                <code className="detail-code">{result.signing_key_id || "transmute-key-2026-v1"}</code>
              </div>
              <div className="detail-item">
                <span className="detail-label">Public Registry Status</span>
                <strong className="detail-value">
                  {result.in_registry ? "✓ Recorded in Public Ledger" : "Offline Signed"}
                </strong>
              </div>
              <div className="detail-item">
                <span className="detail-label">Deliverable Revision</span>
                <strong className="detail-value">Rev #{result.revision || 1}</strong>
              </div>
            </div>

            {result.computed_hash && (
              <div className="result-hash-box">
                <div className="hash-header">
                  <span>SHA-256 Content Fingerprint:</span>
                  <button
                    type="button"
                    className="ghost xs"
                    onClick={() => navigator.clipboard.writeText(result.computed_hash)}
                  >
                    Copy Hash
                  </button>
                </div>
                <code className="hash-string">{result.computed_hash}</code>
              </div>
            )}

            {result.timestamp && (
              <div className="result-timestamp muted">
                Certified Timestamp: {new Date(result.timestamp).toUTCString()}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
