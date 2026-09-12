import { initializeApp, getApps, getApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  signOut,
  sendPasswordResetEmail,
  type Auth,
} from "firebase/auth";
import type { User, UserType } from "./types";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID || "",
};

export const isFirebaseConfigured: boolean = Boolean(
  firebaseConfig.apiKey &&
  firebaseConfig.projectId &&
  firebaseConfig.apiKey.trim().length > 5 &&
  !firebaseConfig.apiKey.includes("your_api_key")
);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let googleProvider: GoogleAuthProvider | null = null;

if (isFirebaseConfigured) {
  try {
    app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    auth = getAuth(app);
    googleProvider = new GoogleAuthProvider();
    googleProvider.setCustomParameters({
      prompt: "select_account",
    });
  } catch (err) {
    console.error("[Transmute Firebase] Failed to initialize Firebase:", err);
  }
}

export { app, auth, googleProvider };

/**
 * Format raw Firebase error objects into human-readable messages
 */
export function formatFirebaseError(error: any): string {
  if (!error) return "An unexpected error occurred.";
  const code = error.code || "";
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Invalid email or password. Please verify your credentials.";
    case "auth/email-already-in-use":
      return "This email is already registered. Please switch to Sign in.";
    case "auth/weak-password":
      return "Password should be at least 6 characters long.";
    case "auth/invalid-email":
      return "Please enter a valid email address.";
    case "auth/popup-closed-by-user":
      return "Google sign-in was closed before completing.";
    case "auth/popup-blocked":
      return "Sign-in popup was blocked by browser. Please allow popups for this site.";
    case "auth/cancelled-popup-request":
      return "Authentication request was cancelled.";
    case "auth/account-exists-with-different-credential":
      return "An account already exists with the same email using a different sign-in method.";
    case "auth/network-request-failed":
      return "Network error. Please check your internet connection and try again.";
    case "auth/too-many-requests":
      return "Access temporarily disabled due to too many failed attempts. Reset password or try later.";
    case "auth/operation-not-allowed":
      return "This sign-in provider is not enabled in the Firebase Console.";
    case "auth/unauthorized-domain":
      return "This domain is not authorized in Firebase Console -> Authentication -> Settings -> Authorized domains.";
    default:
      return error.message || "Authentication failed. Please try again.";
  }
}

/**
 * Asynchronously notify the backend DB about authenticated user details (best effort)
 */
export async function syncUserWithBackend(user: User): Promise<void> {
  try {
    await fetch("/api/auth/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: user.name,
        email: user.email,
        user_type: user.userType,
        organisation: user.organisation || null,
      }),
    });
  } catch {
    // Non-blocking if backend is offline or unreachable
  }
}

/**
 * Sign in using Google OAuth (Gmail)
 */
export async function signInWithGoogle(
  userType: UserType = "Organisation",
  organisation?: string
): Promise<User> {
  if (!isFirebaseConfigured || !auth || !googleProvider) {
    throw new Error(
      "Firebase credentials are not configured. Please set your keys in frontend/.env."
    );
  }

  const result = await signInWithPopup(auth, googleProvider);
  const fbUser = result.user;

  // Check if we have an existing local profile to preserve userType and organization
  let finalUserType = userType;
  let finalOrg = organisation;
  const saved = localStorage.getItem("tx.user");
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      if (parsed.email === fbUser.email) {
        if (parsed.userType) finalUserType = parsed.userType;
        if (parsed.organisation) finalOrg = parsed.organisation;
      }
    } catch {
      // ignore
    }
  }

  const appUser: User = {
    id: fbUser.uid,
    uid: fbUser.uid,
    name: fbUser.displayName || fbUser.email?.split("@")[0] || "User",
    email: fbUser.email || "",
    userType: finalUserType,
    organisation: finalOrg?.trim() || undefined,
    photoURL: fbUser.photoURL || undefined,
  };

  localStorage.setItem("tx.user", JSON.stringify(appUser));
  await syncUserWithBackend(appUser);
  return appUser;
}

/**
 * Sign in with email and password
 */
export async function signInWithEmail(email: string, password: string): Promise<User> {
  if (!isFirebaseConfigured || !auth) {
    throw new Error(
      "Firebase credentials are not configured. Please set your keys in frontend/.env."
    );
  }

  const result = await signInWithEmailAndPassword(auth, email.trim(), password);
  const fbUser = result.user;

  let userType: UserType = "Organisation";
  let organisation: string | undefined;
  const saved = localStorage.getItem("tx.user");
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      if (parsed.email === fbUser.email) {
        if (parsed.userType) userType = parsed.userType;
        if (parsed.organisation) organisation = parsed.organisation;
      }
    } catch {
      // ignore
    }
  }

  const appUser: User = {
    id: fbUser.uid,
    uid: fbUser.uid,
    name: fbUser.displayName || email.split("@")[0],
    email: fbUser.email || email.trim(),
    userType,
    organisation,
    photoURL: fbUser.photoURL || undefined,
  };

  localStorage.setItem("tx.user", JSON.stringify(appUser));
  await syncUserWithBackend(appUser);
  return appUser;
}

/**
 * Create a new account with email and password
 */
export async function signUpWithEmail(
  email: string,
  password: string,
  name: string,
  userType: UserType,
  organisation?: string
): Promise<User> {
  if (!isFirebaseConfigured || !auth) {
    throw new Error(
      "Firebase credentials are not configured. Please set your keys in frontend/.env."
    );
  }

  const result = await createUserWithEmailAndPassword(auth, email.trim(), password);
  const fbUser = result.user;

  if (name.trim()) {
    try {
      await updateProfile(fbUser, { displayName: name.trim() });
    } catch (err) {
      console.warn("[Firebase] Could not update displayName:", err);
    }
  }

  const appUser: User = {
    id: fbUser.uid,
    uid: fbUser.uid,
    name: name.trim() || email.split("@")[0],
    email: fbUser.email || email.trim(),
    userType,
    organisation: organisation?.trim() || undefined,
    photoURL: fbUser.photoURL || undefined,
  };

  localStorage.setItem("tx.user", JSON.stringify(appUser));
  await syncUserWithBackend(appUser);
  return appUser;
}

/**
 * Trigger Firebase Password Reset Email
 */
export async function resetPassword(email: string): Promise<void> {
  if (!isFirebaseConfigured || !auth) {
    throw new Error(
      "Firebase credentials are not configured. Please set your keys in frontend/.env."
    );
  }
  await sendPasswordResetEmail(auth, email.trim());
}

/**
 * Sign out from Firebase and clear local session
 */
export async function logoutUser(): Promise<void> {
  if (auth) {
    try {
      await signOut(auth);
    } catch (err) {
      console.warn("[Firebase] Error during signOut:", err);
    }
  }
  localStorage.removeItem("tx.user");
}

/**
 * Fallback local demo mode sign in when Firebase is unconfigured or during testing
 */
export function loginDemo(
  email: string,
  userType: UserType = "Organisation",
  name?: string,
  organisation?: string
): User {
  const finalEmail = email.trim() || "analyst@transmute.intel";
  const appUser: User = {
    id: "demo-local-" + Date.now(),
    name: name?.trim() || finalEmail.split("@")[0] || "Demo Analyst",
    email: finalEmail,
    userType,
    organisation: organisation?.trim() || "Threat Intelligence Unit",
  };
  localStorage.setItem("tx.user", JSON.stringify(appUser));
  syncUserWithBackend(appUser).catch(() => {});
  return appUser;
}
