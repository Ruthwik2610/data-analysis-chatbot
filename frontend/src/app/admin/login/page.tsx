"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Lock, Sparkles } from "lucide-react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { token, user_token } = await api.adminLogin(password);
      localStorage.setItem("datachat_admin_token", token);
      if (user_token) {
        localStorage.setItem("datachat_user_token", user_token);
      }
      router.push("/admin");
    } catch (err: any) {
      setError(err.message || "Invalid password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-primary">
      <div 
        className="w-full max-w-md p-8 rounded-2xl shadow-xl"
        style={{ 
          background: "var(--color-background-secondary)", 
          border: "0.5px solid var(--color-border-tertiary)" 
        }}
      >
        <div className="flex flex-col items-center mb-8">
          <div 
            className="p-4 rounded-full mb-4"
            style={{ background: "var(--color-background-primary)", color: "var(--color-text-info)" }}
          >
            <Lock size={32} />
          </div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--color-text-primary)" }}>
            Unipro Control Center
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--color-text-tertiary)" }}>
            Enter your passcode to access insights
          </p>
        </div>

        <div 
          className="mb-8 p-4 rounded-xl border flex flex-col gap-1.5 animate-pulse"
          style={{ 
            background: "rgba(37, 99, 235, 0.05)", 
            borderColor: "rgba(37, 99, 235, 0.15)" 
          }}
        >
          <div className="text-[10px] font-bold uppercase tracking-widest text-blue-500 flex items-center gap-1.5">
            <Sparkles size={12} /> Testing Mode Active
          </div>
          <div className="text-xs text-white/50">
            Use passcode: <span className="font-mono text-blue-400 font-bold">admin123</span>
          </div>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Admin Passcode"
              className="w-full px-4 py-3 rounded-xl outline-none transition-all"
              style={{ 
                background: "var(--color-background-primary)", 
                border: "1px solid var(--color-border-secondary)",
                color: "var(--color-text-primary)"
              }}
              autoFocus
            />
          </div>

          {error && (
            <div className="text-red-500 text-sm text-center font-medium">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold transition-all disabled:opacity-50"
            style={{ 
              background: "var(--color-text-info)", 
              color: "white" 
            }}
          >
            {loading ? "Verifying..." : "Unlock Dashboard"}
          </button>
        </form>

        <div className="mt-8 text-center">
          <button 
            onClick={() => router.push("/")}
            className="text-xs"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            ← Return to Chat
          </button>
        </div>
      </div>
    </div>
  );
}
