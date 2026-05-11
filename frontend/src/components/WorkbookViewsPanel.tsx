"use client";

import { useEffect, useState } from "react";
import { Cloud, GitMerge, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { WorkbookView } from "@/lib/types";

const PUBLIC_BASE = "https://unipro.share.zrok.io";

export function WorkbookViewsPanel({ connectorId, connectorName }: { connectorId: string; connectorName: string }) {
  const [views, setViews] = useState<WorkbookView[]>([]);
  const [viewName, setViewName] = useState("");
  const [viewSql, setViewSql] = useState("");
  const [mergeName, setMergeName] = useState("");
  const [leftTable, setLeftTable] = useState("");
  const [rightTable, setRightTable] = useState("");
  const [leftKey, setLeftKey] = useState("");
  const [rightKey, setRightKey] = useState("");
  const [editName, setEditName] = useState("");
  const [editSql, setEditSql] = useState("");
  const [workerUrl, setWorkerUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const loadViews = async () => {
    setViews(await api.listWorkbookViews(connectorId));
  };

  useEffect(() => {
    loadViews().catch(console.error);
  }, [connectorId]);

  const createView = async () => {
    if (!viewName.trim() || !viewSql.trim()) return;
    setBusy(true);
    try {
      await api.createWorkbookView(connectorId, { name: viewName.trim(), sql: viewSql.trim() });
      setViewName("");
      setViewSql("");
      await loadViews();
    } finally {
      setBusy(false);
    }
  };

  const mergeTables = async () => {
    if (!mergeName.trim() || !leftTable.trim() || !rightTable.trim() || !leftKey.trim() || !rightKey.trim()) return;
    setBusy(true);
    try {
      await api.mergeWorkbookView(connectorId, {
        name: mergeName.trim(),
        left_table: leftTable.trim(),
        right_table: rightTable.trim(),
        left_key: leftKey.trim(),
        right_key: rightKey.trim(),
        join_type: "inner",
      });
      setMergeName("");
      await loadViews();
    } finally {
      setBusy(false);
    }
  };

  const expose = async () => {
    setBusy(true);
    try {
      const deployment = await api.deployWorkbookCloudflare(connectorId, { public_base_url: PUBLIC_BASE });
      setWorkerUrl(deployment.worker_url);
    } finally {
      setBusy(false);
    }
  };

  const deleteView = async (name: string) => {
    await api.deleteWorkbookView(connectorId, name);
    await loadViews();
  };

  const modifyView = async () => {
    if (!editName || !editSql.trim()) return;
    setBusy(true);
    try {
      await api.updateWorkbookView(connectorId, editName, { sql: editSql.trim() });
      setEditSql("");
      await loadViews();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-emerald-500/10 bg-emerald-500/[0.04] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-primary">{connectorName}</p>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400/70">Workbook views</p>
        </div>
        <button
          onClick={expose}
          disabled={busy}
          className="flex items-center gap-2 rounded-xl border border-emerald-400/20 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-200 hover:bg-emerald-400/10 disabled:opacity-40"
        >
          <Cloud size={13} />
          Expose through Cloudflare
        </button>
      </div>
      {workerUrl && <p className="mb-4 truncate rounded-xl bg-black/20 px-3 py-2 text-xs text-emerald-100">{workerUrl}</p>}

      <div className="grid grid-cols-1 gap-3">
        <input
          aria-label="View name"
          value={viewName}
          onChange={(e) => setViewName(e.target.value)}
          className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none"
          placeholder="view_name"
        />
        <textarea
          aria-label="View SQL"
          value={viewSql}
          onChange={(e) => setViewSql(e.target.value)}
          className="min-h-[72px] resize-none rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none"
          placeholder="SELECT ... FROM workbook_table"
        />
        <button onClick={createView} disabled={busy} className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white disabled:opacity-40">
          <Plus size={13} />
          Create view
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <input aria-label="Merge view name" value={mergeName} onChange={(e) => setMergeName(e.target.value)} className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none" placeholder="merged_view" />
        <input aria-label="Left table" value={leftTable} onChange={(e) => setLeftTable(e.target.value)} className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none" placeholder="orders" />
        <input aria-label="Right table" value={rightTable} onChange={(e) => setRightTable(e.target.value)} className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none" placeholder="customers" />
        <input aria-label="Left key" value={leftKey} onChange={(e) => setLeftKey(e.target.value)} className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none" placeholder="order_id" />
        <input aria-label="Right key" value={rightKey} onChange={(e) => setRightKey(e.target.value)} className="rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none" placeholder="order_id" />
        <button onClick={mergeTables} disabled={busy} className="flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white disabled:opacity-40">
          <GitMerge size={13} />
          Merge tables
        </button>
      </div>

      <div className="mt-4 flex flex-col gap-2">
        {views.map((view) => (
          <div key={view.id || view.name} className="flex items-center justify-between gap-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-bold text-primary">{view.name}</p>
              <p className="truncate text-[10px] text-secondary">{view.row_count} rows · {(view.columns || []).join(", ")}</p>
            </div>
            <button onClick={() => { setEditName(view.name); setEditSql(view.sql || ""); }} className="rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-emerald-200 hover:bg-emerald-500/10">
              Modify
            </button>
            <button aria-label={`Delete ${view.name}`} onClick={() => deleteView(view.name)} className="rounded-lg p-2 text-tertiary hover:bg-red-500/10 hover:text-red-400">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      {editName && (
        <div className="mt-4 grid grid-cols-1 gap-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-300">Modify {editName}</p>
          <textarea
            aria-label="Modify view SQL"
            value={editSql}
            onChange={(e) => setEditSql(e.target.value)}
            className="min-h-[72px] resize-none rounded-xl border border-secondary bg-secondary px-3 py-2 text-xs text-primary outline-none"
          />
          <button onClick={modifyView} disabled={busy} className="rounded-xl bg-emerald-700 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white disabled:opacity-40">
            Modify view
          </button>
        </div>
      )}
    </div>
  );
}
