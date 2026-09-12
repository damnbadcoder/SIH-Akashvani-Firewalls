import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { UserType } from "../lib/types";
import {
  isFirebaseConfigured,
  signInWithGoogle,
  signInWithEmail,
  signUpWithEmail,
  resetPassword,
  loginDemo,
  formatFirebaseError,
} from "../lib/firebase";

const USER_TYPES: UserType[] = [
  "Organisation",
  "Government Agency",
  "Influencer",
  "Researcher",
  "Journalist",
  "Individual",
];

const TYPE_DESC: Record<UserType, string> = {
  Organisation: "Corporate comms, SOC and security teams",
  "Government Agency": "Ministries, CERTs and public bodies",
  Influencer: "Creators distributing public-facing content",
  Researcher: "Analysts publishing findings and reports",
  Journalist: "Media covering incidents and policy",
  Individual: "Personal and ad-hoc use",
};

export default function Auth() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [userType, setUserType] = useState<UserType>("Organisation");

  const [error, setError] = useState("");
  const [infoMessage, setInfoMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  // Handle Google OAuth (Gmail) Login / Sign Up
  async function handleGoogleLogin() {
    setError("");
    setInfoMessage("");

    if (!isFirebaseConfigured) {
      loginDemo(
        "alex.threatintel@gmail.com",
        userType,
        name.trim() || "Alex Vance (Google)",
        organisation || "Threat Intelligence Group"
      );
      navigate("/", { replace: true });
      return;
    }

    setGoogleLoading(true);
    try {
      await signInWithGoogle(userType, organisation);
      navigate("/", { replace: true });
    } catch (err: any) {
      setError(formatFirebaseError(err));
    } finally {
      setGoogleLoading(false);
    }
  }

  // Handle Email/Password Login or Sign Up
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setInfoMessage("");

    if (!email.trim() || !password.trim()) {
      return setError("Email and password are required.");
    }
    if (mode === "signup" && !name.trim()) {
      return setError("Full name is required to create an account.");
    }

    // If Firebase is not configured, fall back gracefully to demo mode
    if (!isFirebaseConfigured) {
      loginDemo(email, userType, name, organisation);
      navigate("/", { replace: true });
      return;
    }

    setLoading(true);
    try {
      if (mode === "signup") {
        await signUpWithEmail(email, password, name, userType, organisation);
      } else {
        await signInWithEmail(email, password);
      }
      navigate("/", { replace: true });
    } catch (err: any) {
      setError(formatFirebaseError(err));
    } finally {
      setLoading(false);
    }
  }

  // Handle Password Reset
  async function handleResetPassword() {
    setError("");
    setInfoMessage("");

    if (!email.trim()) {
      return setError("Please enter your email address above to receive a password reset link.");
    }

    if (!isFirebaseConfigured) {
      return setError("Firebase is not configured. Add your Firebase keys to frontend/.env.");
    }

    try {
      await resetPassword(email);
      setInfoMessage(`Password reset link sent to ${email.trim()}. Please check your inbox.`);
    } catch (err: any) {
      setError(formatFirebaseError(err));
    }
  }

  // Instant Demo Mode Bypass
  function handleDemoBypass() {
    loginDemo(
      email || "analyst@transmute.intel",
      userType,
      name || "Demo Analyst",
      organisation || "Cyber Defense Unit"
    );
    navigate("/", { replace: true });
  }

  return (
    <div className="auth">
      <aside className="auth-brand">
        <div className="logo-mark">⌁</div>
        <h1>Transmute</h1>
        <p className="auth-tagline">
          One source. Every deliverable. Transform reports, advisories and raw intelligence into
          publication-ready artefacts.
        </p>
        <ul className="auth-points">
          <li>Multi-format source ingestion</li>
          <li>9 output types from a single run</li>
          <li>Editable markdown deliverables</li>
          <li>Enterprise-grade Google &amp; Firebase authentication</li>
        </ul>
      </aside>

      <main className="auth-panel">
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="segmented">
            <button
              type="button"
              className={mode === "login" ? "on" : ""}
              onClick={() => {
                setMode("login");
                setError("");
                setInfoMessage("");
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "signup" ? "on" : ""}
              onClick={() => {
                setMode("signup");
                setError("");
                setInfoMessage("");
              }}
            >
              Create account
            </button>
          </div>

          {!isFirebaseConfigured && (
            <div className="auth-config-notice">
              <span className="notice-icon">⚙️</span>
              <div className="notice-body">
                <strong>Firebase Setup Note:</strong> Fill in <code>frontend/.env</code> with your
                Firebase project keys to activate live Google/Email authentication.
              </div>
            </div>
          )}

          {/* Google Sign-in Option */}
          <button
            type="button"
            className="google-btn"
            onClick={handleGoogleLogin}
            disabled={googleLoading || loading}
            aria-label="Continue with Google"
          >
            <svg className="google-icon" viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3h3.86c2.26-2.09 3.68-5.17 3.68-9.09z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.27 14.29c-.25-.72-.38-1.49-.38-2.29s.13-1.57.38-2.29V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.98-3.09z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09c.95-2.85 3.6-4.96 6.73-4.96z"
              />
            </svg>
            <span>
              {googleLoading
                ? "Connecting to Google..."
                : mode === "login"
                ? "Continue with Google"
                : "Sign up with Google"}
            </span>
          </button>

          <div className="auth-divider">
            <span>or continue with email</span>
          </div>

          {mode === "signup" && (
            <>
              <label>
                Full name
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Aditi Sharma"
                  autoFocus
                  required
                />
              </label>
              <label>
                Organisation <span className="opt">(optional)</span>
                <input
                  value={organisation}
                  onChange={(e) => setOrganisation(e.target.value)}
                  placeholder="Acme Corp / CERT-In"
                />
              </label>
            </>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@organisation.gov"
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>

          {mode === "login" && (
            <div className="auth-row-sub">
              <button
                type="button"
                className="forgot-link"
                onClick={handleResetPassword}
              >
                Forgot password?
              </button>
            </div>
          )}

          {mode === "signup" && (
            <fieldset className="user-types">
              <legend>Account type</legend>
              <div className="type-grid">
                {USER_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={userType === t ? "on" : ""}
                    onClick={() => setUserType(t)}
                    title={TYPE_DESC[t]}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <p className="type-desc">{TYPE_DESC[userType]}</p>
            </fieldset>
          )}

          {error && <p className="form-error">{error}</p>}
          {infoMessage && <p className="form-success">{infoMessage}</p>}

          <button className="primary" type="submit" disabled={loading || googleLoading}>
            {loading ? "Authenticating..." : mode === "login" ? "Sign in" : "Create account"}
          </button>

          {!isFirebaseConfigured && (
            <button
              type="button"
              className="demo-mode-btn"
              onClick={handleDemoBypass}
            >
              ⚡ Continue in Demo Mode (Local)
            </button>
          )}

          <p className="auth-note">
            Protected by Firebase Authentication · Google Identity Provider
          </p>
        </form>
      </main>
    </div>
  );
}
