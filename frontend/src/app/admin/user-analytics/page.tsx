"use client";

import { useEffect, useState } from "react";
import { AlertCircle, MessageSquare, WholeWord } from "lucide-react";
import { api } from "@/lib/api";

export default function UserAnalyticsPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.getUserAnalytics().then(setData).catch(console.error);
  }, []);

  if (!data) {
    return <div className="flex-1 bg-primary p-8 text-sm text-white/40">Loading user analytics...</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto bg-primary p-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        <div>
          <h1 className="text-2xl font-semibold text-white">User Analytics</h1>
          <p className="mt-1 text-xs font-medium text-white/40">Behavior, comfort signals, vocabulary, and reported friction from chat usage.</p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Metric label="Messages sampled" value={data.message_sample_size} />
          <Metric label="Feedback groups" value={data.feedback_summary?.length || 0} />
          <Metric label="Recent errors" value={data.recent_errors?.length || 0} />
        </div>
        <section className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40"><WholeWord size={13} /> Vocabulary</h2>
          <div className="flex flex-wrap gap-2">
            {(data.vocabulary || []).map((item: any) => (
              <span key={item.term} className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-300">{item.term} <span className="text-blue-300/50">{item.count}</span></span>
            ))}
          </div>
        </section>
        <section className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40"><WholeWord size={13} /> Industry Glossary Candidates</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(data.industry_vocabulary || []).map((item: any) => (
              <div key={`${item.industry}-${item.term}`} className="rounded-2xl bg-white/5 p-4 text-sm text-white/70">
                <div className="font-semibold">{item.term} · {item.industry}</div>
                <div className="mt-1 text-xs text-white/35">{item.project_count} projects{item.columns?.length ? ` · ${item.columns.join(", ")}` : ""}</div>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40"><MessageSquare size={13} /> Feedback Signals</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(data.feedback_summary || []).map((item: any, index: number) => (
              <div key={index} className="rounded-2xl bg-white/5 p-4 text-sm text-white/70">
                <div className="font-semibold">{item.category} · {item.status}</div>
                <div className="mt-1 text-xs text-white/35">rating {item.rating} · {item.count} reports</div>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-[28px] border border-white/5 bg-white/[0.03] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-white/40"><AlertCircle size={13} /> Error Page</h2>
          <div className="flex flex-col gap-3">
            {(data.recent_errors || []).map((item: any) => (
              <a key={item.id} href={`/?chat_id=${encodeURIComponent(item.chat_id)}`} className="rounded-2xl bg-red-500/5 p-4 text-sm text-red-100/80">
                <div className="font-semibold">{item.chat_title || item.chat_id}</div>
                <div className="mt-1 text-xs text-red-100/50">{item.content}</div>
              </a>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
      <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/35">{label}</div>
      <div className="mt-2 text-3xl font-bold text-white">{value}</div>
    </div>
  );
}
