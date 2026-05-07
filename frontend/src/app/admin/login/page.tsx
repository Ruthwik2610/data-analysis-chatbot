"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Lock } from "lucide-react";

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
      const { token } = await api.adminLogin(password);
      localStorage.setItem("datachat_admin_token", token);
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
            Admin Login
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--color-text-tertiary)" }}>
            Enter your passcode to access insights
          </p>
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
