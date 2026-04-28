"use client";

import { AlertCircle, Plug, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Connector, MCPConnector, Source } from "@/lib/types";

const MCP_STORAGE_KEY = "datachat_saved_mcp_connectors";

type SavedMCP = { name: string; url: string };

function readSavedMCPs(): SavedMCP[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(MCP_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SavedMCP[]) : [];
  } catch {
    return [];
  }
}

function writeSavedMCPs(list: SavedMCP[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MCP_STORAGE_KEY, JSON.stringify(list));
}

function notifySourcesChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("data-chat:sources-changed"));
}

interface ConnectorPopoverProps {
  open: boolean;
  onClose: () => void;
  onAttached: (source: Source) => void;
  anchorRef: React.RefObject<HTMLElement | null>;
}

export function ConnectorPopover({ open, onClose, onAttached, anchorRef }: ConnectorPopoverProps) {
  const [tab, setTab] = useState<"api" | "mcp">("api");
  const [url, setUrl] = useState("");
  const [auth, setAuth] = useState("");

  // MCP agent-loop state (replaces the legacy tool_args UI)
  const [bridgeUrl, setBridgeUrl] = useState("");
  const [bridgeName, setBridgeName] = useState("");
  const [mcpConnectors, setMcpConnectors] = useState<MCPConnector[]>([]);

  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const popRef = useRef<HTMLDivElement>(null);

  const refreshMCP = useCallback(async () => {
    try {
      const list = await api.listMCPConnectors();
      setMcpConnectors(list);
    } catch {
      // pool unreachable — leave list as-is
    }
  }, []);

  // Auto-reconnect saved MCPs that the server doesn't already know about.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      const live = await api.listMCPConnectors().catch(() => [] as MCPConnector[]);
      if (cancelled) return;
      setMcpConnectors(live);
      const liveUrls = new Set(live.map((c) => c.url));
      for (const s of readSavedMCPs()) {
        if (cancelled) return;
        if (liveUrls.has(s.url)) continue;
        try {
          await api.addMCPConnector(s.url, s.name);
        } catch {
          // ignore — health loop will retry
        }
      }
      if (!cancelled) {
        await refreshMCP();
        notifySourcesChanged();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, refreshMCP]);

  // 5-second poll of MCP status while the popover is open.
  useEffect(() => {
    if (!open) return;
    const t = window.setInterval(refreshMCP, 5000);
    return () => window.clearInterval(t);
  }, [open, refreshMCP]);

  useEffect(() => {
    if (!open) return;
    api.listConnectors().then(setConnectors).catch(() => {});

    setError(null);
    const onDown = (e: MouseEvent) => {
      if (popRef.current?.contains(e.target as Node)) return;
      if (anchorRef.current?.contains(e.target as Node)) return;
      onClose();
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (tab === "api") {
        if (!url.trim()) throw new Error("Paste a URL.");
        const src = await api.attachAPI(url.trim(), auth.trim() || null, save);
        setUrl("");
        setAuth("");
        onAttached(src);
        setSave(false);
        onClose();
      } else {
        const bridge = bridgeUrl.trim();
        if (!bridge) throw new Error("Paste a bridge URL.");
        const name = bridgeName.trim() || bridge;
        const conn = await api.addMCPConnector(bridge, name);
        if (save) {
          const list = readSavedMCPs().filter((s) => s.url !== bridge);
          list.push({ name, url: bridge });
          writeSavedMCPs(list);
        }
        setBridgeUrl("");
        setBridgeName("");
        setSave(false);
        await refreshMCP();
        notifySourcesChanged();
        // Don't close — let the user see the green dot appear in the saved list.
        if (conn.status !== "connected") {
          setError(conn.last_error || "Connector reported a non-connected status");
        }
      }
    } catch (e: any) {
      setError(e?.message || "Connection failed");
    } finally {
      setBusy(false);
    }
  };

  const useSaved = async (id: string) => {
    setBusy(true);
    try {
      const src = await api.useConnector(id);
      onAttached(src);
      onClose();
    } catch (e: any) {
      setError(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const removeMCP = async (id: string) => {
    const target = mcpConnectors.find((c) => c.id === id);
    setBusy(true);
    try {
      await api.removeMCPConnector(id);
      if (target) {
        writeSavedMCPs(readSavedMCPs().filter((s) => s.url !== target.url));
      }
      await refreshMCP();
      notifySourcesChanged();
    } catch (e: any) {
      setError(e?.message || "Failed to disconnect");
    } finally {
      setBusy(false);
    }
  };

  const reconnectMCP = async (c: MCPConnector) => {
    setBusy(true);
    try {
      await api.updateMCPConnector(c.id, { url: c.url, name: c.name });
      await refreshMCP();
      notifySourcesChanged();
    } catch (e: any) {
      setError(e?.message || "Reconnect failed");
    } finally {
      setBusy(false);
    }
  };

  const submitDisabled = busy || (tab === "api" ? !url.trim() : !bridgeUrl.trim());

  return (
    <div
      ref={popRef}
      className="absolute bottom-[calc(100%+8px)] left-0 z-30 w-[380px] fade-in"
      style={{
        background: "var(--color-background-primary)",
        border: "0.5px solid var(--color-border-secondary)",
        borderRadius: 12,
        boxShadow: "var(--shadow-lg)",
      }}
    >
      <div
        className="flex items-center justify-between px-3 py-2"
        style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div className="flex items-center gap-2 text-[12.5px] font-medium">
          <Plug size={13} strokeWidth={1.5} />
          Connect a source
        </div>
        <button onClick={onClose} className="p-1 rounded-md" style={{ color: "var(--color-text-tertiary)" }}>
          <X size={12} />
        </button>
      </div>

      <div className="px-3 pt-3 flex gap-4 text-[11px] font-medium uppercase tracking-wider">
        <button
          onClick={() => setTab("api")}
          style={{ color: tab === "api" ? "var(--color-text-primary)" : "var(--color-text-tertiary)" }}
        >
          JSON API
        </button>
        <button
          onClick={() => setTab("mcp")}
          style={{ color: tab === "mcp" ? "var(--color-text-primary)" : "var(--color-text-tertiary)" }}
        >
          MCP Bridge
        </button>
      </div>

      <div className="p-3 space-y-2">
        {tab === "api" ? (
          <>
            <input
              autoFocus
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="https://api.example.com/data"
              className="w-full px-2.5 py-1.5 text-[12.5px] rounded-md outline-none"
              style={{
                background: "var(--color-background-primary)",
                border: "0.5px solid var(--color-border-secondary)",
                color: "var(--color-text-primary)",
              }}
            />
            <input
              value={auth}
              onChange={(e) => setAuth(e.target.value)}
              type="password"
              placeholder="Bearer token (optional)"
              className="w-full px-2.5 py-1.5 text-[12.5px] rounded-md outline-none"
              style={{
                background: "var(--color-background-primary)",
                border: "0.5px solid var(--color-border-secondary)",
                color: "var(--color-text-primary)",
              }}
            />
          </>
        ) : (
          <>
            <input
              autoFocus
              value={bridgeName}
              onChange={(e) => setBridgeName(e.target.value)}
              placeholder="Server name (optional, e.g. BigQuery)"
              className="w-full px-2.5 py-1.5 text-[12.5px] rounded-md outline-none"
              style={{
                background: "var(--color-background-primary)",
                border: "0.5px solid var(--color-border-secondary)",
                color: "var(--color-text-primary)",
              }}
            />
            <input
              value={bridgeUrl}
              onChange={(e) => setBridgeUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Bridge URL (https://example.com/mcp)"
              className="w-full px-2.5 py-1.5 text-[12.5px] rounded-md outline-none"
              style={{
                background: "var(--color-background-primary)",
                border: "0.5px solid var(--color-border-secondary)",
                color: "var(--color-text-primary)",
              }}
            />
            <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
              The model will discover and call the bridge&apos;s tools per question — no per-arg form.
            </div>

            <MCPList
              connectors={mcpConnectors}
              busy={busy}
              onReconnect={reconnectMCP}
              onRemove={removeMCP}
            />
          </>
        )}

        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-1.5 text-[11.5px]" style={{ color: "var(--color-text-secondary)" }}>
            <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} />
            Save link
          </label>
          <button
            onClick={submit}
            disabled={submitDisabled}
            className="px-3 py-1 text-[12px] rounded-md font-medium transition-opacity"
            style={{
              background: "var(--color-text-primary)",
              color: "var(--color-background-primary)",
              opacity: submitDisabled ? 0.4 : 1,
            }}
          >
            {busy ? "…" : "Connect"}
          </button>
        </div>
        {error && (
          <div
            className="text-[11px] px-2 py-1.5 rounded-md"
            style={{
              background: "rgba(220,38,38,0.06)",
              color: "#dc2626",
              border: "0.5px solid rgba(220,38,38,0.2)",
            }}
          >
            {error}
          </div>
        )}
      </div>

      {connectors.filter((c) => c.kind === "api").length > 0 && (
        <div className="px-3 pb-3 pt-2" style={{ borderTop: "0.5px solid var(--color-border-tertiary)" }}>
          <div
            className="text-[10.5px] uppercase mb-1.5"
            style={{ color: "var(--color-text-tertiary)", letterSpacing: "0.06em" }}
          >
            Saved APIs
          </div>
          <div className="space-y-1">
            {connectors.filter((c) => c.kind === "api").map((c) => (
              <div key={c.id} className="flex items-center gap-2 group">
                <button
                  onClick={() => useSaved(c.id)}
                  className="flex-1 min-w-0 text-left text-[12px] truncate px-2 py-1 rounded-md transition-colors"
                  style={{ color: "var(--color-text-secondary)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-secondary)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  title={c.label}
                >
                  <span className="uppercase mr-1.5 text-[10px]" style={{ color: "var(--color-text-tertiary)" }}>
                    {c.kind}
                  </span>
                  {c.label}
                </button>
                <button
                  onClick={async () => {
                    await api.deleteConnector(c.id);
                    setConnectors((s) => s.filter((x) => x.id !== c.id));
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded"
                  style={{ color: "var(--color-text-tertiary)" }}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  connected: "#10b981",
  connecting: "#f59e0b",
  error: "#ef4444",
};

function MCPList({
  connectors,
  busy,
  onReconnect,
  onRemove,
}: {
  connectors: MCPConnector[];
  busy: boolean;
  onReconnect: (c: MCPConnector) => void | Promise<void>;
  onRemove: (id: string) => void | Promise<void>;
}) {
  if (connectors.length === 0) {
    return (
      <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
        No MCP bridges connected yet.
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <div className="text-[10.5px] uppercase" style={{ color: "var(--color-text-tertiary)", letterSpacing: "0.06em" }}>
        Connected bridges
      </div>
      {connectors.map((c) => {
        const color = STATUS_COLOR[c.status] || STATUS_COLOR.error;
        const toolCount = c.tools?.length ?? 0;
        return (
          <div
            key={c.id}
            className="flex items-start gap-2 px-2 py-1.5 rounded-md group"
            style={{ background: "var(--color-background-secondary)" }}
          >
            <span
              title={c.status}
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: color,
                marginTop: 6,
                flexShrink: 0,
              }}
            />
            <div className="flex-1 min-w-0">
              <div className="text-[12px] truncate" style={{ color: "var(--color-text-primary)" }} title={c.url}>
                {c.name}
              </div>
              <div className="text-[10.5px]" style={{ color }}>
                {c.status === "connected" ? `${toolCount} tools` : c.status === "connecting" ? "Connecting…" : (c.last_error || "Error")}
              </div>
              {c.status === "error" && c.last_error && (
                <div className="text-[10.5px] mt-0.5 flex items-start gap-1" style={{ color: "var(--color-text-tertiary)" }}>
                  <AlertCircle size={10} style={{ marginTop: 1, flexShrink: 0 }} />
                  <span className="truncate" title={c.last_error}>{c.last_error}</span>
                </div>
              )}
            </div>
            <button
              onClick={() => onReconnect(c)}
              disabled={busy || c.status === "connecting"}
              className="opacity-60 hover:opacity-100 p-1 rounded transition-opacity"
              style={{ color: "var(--color-text-tertiary)" }}
              title="Reconnect"
            >
              <RefreshCw size={11} />
            </button>
            <button
              onClick={() => onRemove(c.id)}
              disabled={busy}
              className="opacity-60 hover:opacity-100 p-1 rounded transition-opacity"
              style={{ color: "#ef4444" }}
              title="Disconnect"
            >
              <Trash2 size={11} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
