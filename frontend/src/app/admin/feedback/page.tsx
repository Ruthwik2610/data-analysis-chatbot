"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";

export default function FeedbackPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getFeedback();
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const updateStatus = async (id: string, status: string) => {
    await api.updateFeedbackStatus(id, status);
    await load();
  };

  return (
    <div className="flex-1 overflow-y-auto bg-primary p-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Feedback Inbox</h1>
          <p className="mt-1 text-xs font-medium text-white/40">User ratings, reports, and bug notes linked back to chat answers and traces.</p>
        </div>
        {loading ? (
          <div className="rounded-[24px] border border-white/5 bg-white/[0.03] p-8 text-sm text-white/40">Loading feedback...</div>
        ) : items.length === 0 ? (
          <div className="rounded-[24px] border border-white/5 bg-white/[0.03] p-8 text-sm text-white/40">No feedback yet.</div>
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <div key={item.id} className="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-widest ${item.rating > 0 ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                        {item.rating > 0 ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                        {item.category || "feedback"}
                      </span>
                      <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-white/30">{item.status}</span>
                      {item.project_name && <span className="text-[10px] font-bold uppercase tracking-widest text-white/30">{item.project_name}</span>}
                    </div>
                    <p className="text-sm font-medium text-white/80">{item.question || "Question unavailable"}</p>
                    <p className="mt-2 text-sm text-white/50">{item.answer || "Answer unavailable"}</p>
                    {item.comment && <p className="mt-3 rounded-xl bg-black/20 p-3 text-xs text-white/70"><MessageSquare className="mr-2 inline" size={13} />{item.comment}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {item.chat_id && (
                      <a href={`/?chat_id=${encodeURIComponent(item.chat_id)}`} className="rounded-xl bg-blue-500/10 p-2 text-blue-400" title="Open chat">
                        <ExternalLink size={15} />
                      </a>
                    )}
                    <button onClick={() => updateStatus(item.id, "resolved")} className="rounded-xl bg-green-500/10 px-3 py-2 text-xs font-bold uppercase tracking-widest text-green-400">Resolve</button>
                    <button onClick={() => updateStatus(item.id, "dismissed")} className="rounded-xl bg-white/5 px-3 py-2 text-xs font-bold uppercase tracking-widest text-white/40">Dismiss</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
