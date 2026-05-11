"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Activity, AlertTriangle, Brain, Database, RotateCw } from "lucide-react";
import { api } from "@/lib/api";
import type { QueryLoopMetricsResponse } from "@/lib/types";

export function QueryLoopMetricsDashboard() {
  const [data, setData] = useState<QueryLoopMetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getQueryLoops().then(setData).catch((err) => setError(err?.message || "Failed to load loop metrics"));
  }, []);

  if (error) {
    return <div className="p-8 text-sm text-red-300">{error}</div>;
  }

  if (!data) {
    return <div className="p-8 text-xs font-bold uppercase tracking-[0.2em] text-white/30">Loading query loops...</div>;
  }

  const summary = data.summary;

  return (
    <div className="flex-1 overflow-y-auto bg-primary p-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-blue-400">Intent depth</p>
          <h1 className="mt-2 text-2xl font-bold text-white">Query Loop Metrics</h1>
          <p className="mt-1 text-xs font-medium text-white/40">Find prompts that trigger repeated tool calls, retries, and long reasoning paths.</p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
          <Metric icon={<Brain size={16} />} label="High-loop queries" value={summary.high_loop_queries} />
          <Metric icon={<Activity size={16} />} label="Tracked queries" value={summary.total_queries} />
          <Metric icon={<Database size={16} />} label="Avg tool calls" value={summary.avg_tool_calls} />
          <Metric icon={<RotateCw size={16} />} label="Avg rounds" value={summary.avg_rounds} />
          <Metric icon={<AlertTriangle size={16} />} label="Tool errors" value={summary.total_tool_errors} />
        </div>

        <div className="overflow-hidden rounded-[24px] border border-white/5 bg-white/[0.03]">
          <div className="grid grid-cols-[1fr_150px_90px_90px_90px] gap-4 border-b border-white/5 px-5 py-3 text-[10px] font-bold uppercase tracking-[0.2em] text-white/35">
            <span>Query</span>
            <span>Route</span>
            <span>Tools</span>
            <span>Rounds</span>
            <span>Errors</span>
          </div>
          {data.queries.length === 0 ? (
            <div className="px-5 py-10 text-sm text-white/35">No loop metrics recorded yet.</div>
          ) : (
            data.queries.map((row) => (
              <div key={row.id} className="grid grid-cols-[1fr_150px_90px_90px_90px] gap-4 border-b border-white/5 px-5 py-4 text-sm text-white/75 last:border-0">
                <div className="min-w-0">
                  <p className="truncate font-medium text-white">{row.question}</p>
                  <p className="mt-1 truncate text-[11px] text-white/35">{row.project_name || row.chat_title || "Unscoped chat"}</p>
                </div>
                <span className="text-xs text-blue-200">{row.route}</span>
                <span>{row.tool_call_count}</span>
                <span>{row.round_count}</span>
                <span className={row.tool_error_count ? "text-red-300" : "text-white/45"}>{row.tool_error_count}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: number | string }) {
  return (
    <div className="rounded-[24px] border border-white/5 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 text-blue-300">{icon}<span className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">{label}</span></div>
      <div className="mt-4 text-2xl font-bold text-white">{value}</div>
    </div>
  );
}
