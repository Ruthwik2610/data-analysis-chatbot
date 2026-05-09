"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import Link from "next/link";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    // Skip auth check for login page
    if (pathname === "/admin/login") {
        setAuthorized(true);
        return;
    }

    const token = localStorage.getItem("datachat_admin_token");
    if (!token) {
      router.replace("/admin/login");
    } else {
      setAuthorized(true);
    }
  }, [router, pathname]);

  if (!authorized) return (
    <div className="flex-1 flex items-center justify-center bg-primary h-screen text-white/20 uppercase tracking-widest text-xs font-bold">
        Authenticating Shell...
    </div>
  );

  const isLogin = pathname === "/admin/login";

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-primary">
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
                <img src="/unipro-icon.svg" alt="Unipro" className="w-5 h-5" />
                <div className="flex items-center gap-6 ml-2">
                    <NavLink href="/admin" active={pathname === "/admin"}>Insights</NavLink>
                    <NavLink href="/admin/observability" active={pathname === "/admin/observability"}>Observability</NavLink>
                    <NavLink href="/admin/testing" active={pathname === "/admin/testing"}>Testing Gateway</NavLink>
                </div>
            </div>

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
            className={`text-[10px] uppercase tracking-[0.2em] font-bold border-b-2 pb-1 transition-all ${active ? 'border-blue-500 text-white' : 'border-transparent text-white/30 hover:text-white/60 hover:border-white/10'}`}
        >
            {children}
        </Link>
    );
}
