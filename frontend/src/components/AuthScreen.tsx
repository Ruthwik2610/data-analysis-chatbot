"use client";

import { useState } from "react";
import { Lock, LogIn, UserPlus } from "lucide-react";
import { api, setAuthToken } from "@/lib/api";
import { getLoginCredentials } from "@/lib/loginCredentials";

interface AuthScreenProps {
  onAuthenticated: (user: { id: string; email: string }) => void;
  initialMode?: "login" | "register";
}

export function AuthScreen({ onAuthenticated, initialMode = "login" }: AuthScreenProps) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const credentials = getLoginCredentials();
  const testCredential = credentials.testUser;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setAuthToken(result.access_token);
      onAuthenticated(result.user);
    } catch (err: any) {
      setError(err?.message || "Could not sign in");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-shell min-h-[100dvh] px-4 py-8">
      <section className="auth-panel w-full max-w-[420px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[10px]" style={{ background: "var(--color-background-info)", color: "var(--color-text-info)" }}>
            <Lock size={18} strokeWidth={1.8} />
          </div>
          <div>
            <h1 className="text-[22px] font-semibold leading-tight" style={{ color: "var(--color-text-primary)" }}>
              {mode === "login" ? "Welcome back" : "Create your workspace"}
            </h1>
            <p className="mt-1 text-[13px]" style={{ color: "var(--color-text-tertiary)" }}>
              Projects, files, and chat history stay tied to your account.
            </p>
          </div>
        </div>

        <div className="mb-5 grid grid-cols-2 rounded-[10px] p-1" style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-tertiary)" }}>
          <button type="button" onClick={() => setMode("login")} className="inline-flex items-center justify-center gap-2 rounded-[8px] px-3 py-2 text-[13px] font-medium" style={{ background: mode === "login" ? "var(--color-background-elevated)" : "transparent", color: "var(--color-text-primary)" }}>
            <LogIn size={14} /> Login
          </button>
          <button type="button" onClick={() => setMode("register")} className="inline-flex items-center justify-center gap-2 rounded-[8px] px-3 py-2 text-[13px] font-medium" style={{ background: mode === "register" ? "var(--color-background-elevated)" : "transparent", color: "var(--color-text-primary)" }}>
            <UserPlus size={14} /> Sign up
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email"
            className="w-full rounded-[10px] px-3.5 py-3 text-[14px] outline-none"
            style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-secondary)", color: "var(--color-text-primary)" }}
            autoComplete="email"
            required
          />
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password"
            className="w-full rounded-[10px] px-3.5 py-3 text-[14px] outline-none"
            style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-secondary)", color: "var(--color-text-primary)" }}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={8}
            required
          />
          {error && <p className="text-[13px] font-medium text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[10px] px-4 py-3 text-[14px] font-semibold disabled:opacity-60"
            style={{ background: "#2563eb", color: "#ffffff", boxShadow: "0 14px 24px -18px rgba(37, 99, 235, 0.9)" }}
          >
            {mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
            {loading ? "Please wait..." : mode === "login" ? "Login" : "Create account"}
          </button>
        </form>

        {mode === "login" && testCredential && (
          <div className="mt-5 rounded-[10px] p-3 text-[12px]" style={{ background: "var(--color-background-secondary)", border: "1px solid var(--color-border-tertiary)", color: "var(--color-text-secondary)" }}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="font-semibold" style={{ color: "var(--color-text-primary)" }}>{testCredential.label}</span>
              <button
                type="button"
                onClick={() => {
                  setEmail(testCredential.email);
                  setPassword(testCredential.password);
                }}
                className="rounded-[7px] px-2 py-1 text-[11px] font-medium"
                style={{ background: "var(--color-background-elevated)", color: "var(--color-text-primary)" }}
              >
                Use
              </button>
            </div>
            <div className="grid gap-1">
              <div className="flex items-center justify-between gap-3">
                <span style={{ color: "var(--color-text-tertiary)" }}>Email</span>
                <code>{testCredential.email}</code>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span style={{ color: "var(--color-text-tertiary)" }}>Password</span>
                <code>{testCredential.password}</code>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
