import { useState } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../lib/useAuth";

export function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuth();
  const [submitting, setSubmitting] = useState(false);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm italic text-ink-faint">loading…</p>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  async function handleLogin() {
    if (submitting) return;
    setSubmitting(true);
    try {
      await login();
    } catch {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-8">
      <div className="text-center">
        <h1 className="text-6xl font-medium tracking-tight sm:text-7xl md:text-8xl">
          Jazz Life
        </h1>
        <p className="mt-6 text-base italic text-ink-mute sm:text-lg">
          An almanac of records, releases &amp; concerts.
        </p>

        <button
          type="button"
          onClick={handleLogin}
          disabled={submitting}
          className="mt-16 border border-ink px-10 py-3 text-sm transition-colors hover:bg-ink hover:text-paper disabled:opacity-50"
        >
          {submitting ? "redirecting…" : "Sign in with Spotify"}
        </button>

        <p className="mt-12 text-xs italic text-ink-faint">invite-only</p>
      </div>
    </div>
  );
}
