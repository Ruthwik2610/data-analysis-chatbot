"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChevronLeft, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { getTheme, setTheme, type Theme } from "@/lib/theme";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [authorized, setAuthorized] = useState(false);
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    setThemeState(getTheme());
  }, []);

  useEffect(() => {
    // Skip auth check for login page
    if (pathname === "/admin/login") {
        setAuthorized(true);
        return;
    }

    setAuthorized(false);
    if (!localStorage.getItem("datachat_admin_token")) {
      router.replace("/admin/login");
      return;
    }

    api.getAdminSession()
      .then(() => setAuthorized(true))
      .catch(() => {
        localStorage.removeItem("datachat_admin_token");
        router.replace("/admin/login");
      });
  }, [router, pathname]);

  if (!authorized) return (
    <div className="flex-1 flex items-center justify-center bg-primary h-screen text-white/20 uppercase tracking-widest text-xs font-bold">
        Authenticating Shell...
    </div>
  );

  const isLogin = pathname === "/admin/login";

  return (
    <div className="admin-theme-scope flex flex-col h-screen overflow-hidden bg-primary">
      {!isLogin && (
        <header 
            className="flex items-center justify-between px-6 py-3 shrink-0 z-50" 
            style={{ borderBottom: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-secondary)" }}
        >
            <Link 
            href="/" 
            className="flex items-center gap-2 text-sm font-medium transition-colors"
            style={{ color: "var(--color-text-secondary)" }}
            onMouseEnter={(e) => e.currentTarget.style.color = "var(--color-text-primary)"}
            onMouseLeave={(e) => e.currentTarget.style.color = "var(--color-text-secondary)"}
            >
            <ChevronLeft size={16} />
            Back to Chat
            </Link>
            
            <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2">
                <img src={theme === "dark" ? "/unipro-full-logo-dark.svg" : "/unipro-full-logo.svg"} alt="Unipro" className="h-6" />
                <div className="flex items-center gap-6 ml-4">
                    <NavLink href="/admin" active={pathname === "/admin"}>Insights</NavLink>
                    <NavLink href="/admin/observability" active={pathname === "/admin/observability"}>Observability</NavLink>
                    <NavLink href="/admin/feedback" active={pathname === "/admin/feedback"}>Feedback</NavLink>
                    <NavLink href="/admin/user-analytics" active={pathname === "/admin/user-analytics"}>Users</NavLink>
                    <NavLink href="/admin/costs" active={pathname === "/admin/costs"}>Costs</NavLink>
                    <NavLink href="/admin/query-loops" active={pathname === "/admin/query-loops"}>Loops</NavLink>
                    <NavLink href="/admin/testing" active={pathname === "/admin/testing"}>Testing Gateway</NavLink>
                </div>
            </div>

            <div className="flex items-center gap-2">
                <button
                    type="button"
                    aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                    title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                    onClick={() => {
                        const next = theme === "dark" ? "light" : "dark";
                        setTheme(next);
                        setThemeState(next);
                    }}
                    className="flex h-8 w-8 items-center justify-center rounded-md transition-colors"
                    style={{ border: "0.5px solid var(--color-border-secondary)", color: "var(--color-text-secondary)" }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "var(--color-background-primary)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                    {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
                </button>
                <button
                onClick={() => {
                    localStorage.removeItem("datachat_admin_token");
                    router.push("/admin/login");
                }}
                className="text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
                style={{ border: "0.5px solid var(--color-border-secondary)", color: "var(--color-text-secondary)" }}
                onMouseEnter={(e) => e.currentTarget.style.background = "var(--color-background-primary)"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                >
                Logout
                </button>
            </div>
        </header>
      )}
      <main className="flex-1 overflow-hidden flex flex-col">
        {children}
      </main>
    </div>
  );
}

function NavLink({ href, active, children }: { href: string, active: boolean, children: React.ReactNode }) {
    return (
        <Link 
            href={href} 
            className="text-[10px] uppercase tracking-[0.2em] font-bold border-b-2 pb-1 transition-all"
            style={{
                borderColor: active ? "#3b82f6" : "transparent",
                color: active ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
            }}
            onMouseEnter={(e) => {
                if (!active) {
                    e.currentTarget.style.color = "var(--color-text-secondary)";
                    e.currentTarget.style.borderColor = "var(--color-border-secondary)";
                }
            }}
            onMouseLeave={(e) => {
                if (!active) {
                    e.currentTarget.style.color = "var(--color-text-tertiary)";
                    e.currentTarget.style.borderColor = "transparent";
                }
            }}
        >
            {children}
        </Link>
    );
}
