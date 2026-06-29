"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";

export default function CostsPage() {
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    api.getAdminStats().then(setStats).catch(console.error);
  }, []);

  if (!stats) {
    return <div className="flex-1 bg-primary p-8 text-sm text-white/40">Loading cost analytics...</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto bg-primary p-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <div>
          <h1 className="text-2xl font-semibold text-white">Cost Analytics</h1>
          <p className="mt-1 text-xs font-medium text-white/40">Token spend split by chat, testing, administrative evaluation, and miscellaneous usage.</p>
        </div>
        <div className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">Spend by purpose</h2>
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.token_usage_by_purpose || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="purpose" stroke="rgba(255,255,255,0.35)" fontSize={11} />
                <YAxis stroke="rgba(255,255,255,0.35)" fontSize={11} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16 }} />
                <Bar dataKey="prompt_tokens" name="Prompt tokens" stackId="tokens" fill="#3b82f6" radius={[8, 8, 0, 0]} />
                <Bar dataKey="completion_tokens" name="Completion tokens" stackId="tokens" fill="#10b981" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {(stats.token_usage_by_purpose || []).map((row: any) => (
            <div key={row.purpose} className="rounded-[20px] border border-white/5 bg-white/[0.03] p-5">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/35">{row.purpose}</div>
              <div className="mt-2 text-2xl font-bold text-white">{row.total_tokens?.toLocaleString?.() || row.total_tokens}</div>
              <div className="mt-1 text-xs text-white/35">
                {row.request_count} requests
                {row.estimated_cost_usd ? ` · $${Number(row.estimated_cost_usd).toFixed(4)}` : ""}
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">Model routing</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(stats.token_usage_by_model_mode || []).map((row: any) => (
              <div key={`${row.requested_model_mode}-${row.effective_model_mode}-${row.model}`} className="rounded-[20px] border border-white/5 bg-black/10 p-5">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/35">
                  {row.requested_model_mode} → {row.effective_model_mode}
                </div>
                <div className="mt-2 truncate text-xs font-mono text-white/50">{row.model}</div>
                <div className="mt-2 text-2xl font-bold text-white">{row.total_tokens?.toLocaleString?.() || row.total_tokens}</div>
                <div className="mt-1 text-xs text-white/35">
                  {row.request_count} requests
                  {row.estimated_cost_usd ? ` · $${Number(row.estimated_cost_usd).toFixed(4)}` : ""}
                </div>
              </div>
            ))}
            {!(stats.token_usage_by_model_mode || []).length && (
              <div className="rounded-[20px] border border-white/5 bg-black/10 p-5 text-xs text-white/35">No model routing data yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
