"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminDashboard } from "@/components/AdminDashboard";
import { ChevronLeft } from "lucide-react";
import Link from "next/link";

export default function AdminPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("datachat_admin_token");
    if (!token) {
      router.replace("/admin/login");
    } else {
      setAuthorized(true);
    }
  }, [router]);

  if (!authorized) return null;

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <header 
        className="flex items-center justify-between px-6 py-3" 
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
        <div className="text-[11px] uppercase tracking-widest font-semibold" style={{ color: "var(--color-text-tertiary)" }}>
          Admin Console
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
      <main className="flex-1 overflow-hidden flex flex-col">
        <AdminDashboard />
      </main>
    </div>
  );
}
