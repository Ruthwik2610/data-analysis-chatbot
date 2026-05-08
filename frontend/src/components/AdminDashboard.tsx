import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Activity, AlertTriangle, Clock, Database, MessageSquare, Zap, ExternalLink, Folder } from "lucide-react";

export function AdminDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [hallucinations, setHallucinations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.getAdminStats(),
      api.getHallucinations()
    ])
      .then(([statsData, halData]) => {
        if (mounted) {
          setStats(statsData);
          setHallucinations(halData);
        }
      })
      .catch(console.error)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => { mounted = false; };
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: "var(--color-text-tertiary)" }}>
        Loading insights...
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex-1 flex items-center justify-center text-red-500">
        Failed to load insights.
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto bg-primary">
      <div className="px-8 py-8 max-w-6xl mx-auto w-full">
        <h1 className="text-2xl font-semibold mb-6" style={{ color: "var(--color-text-primary)" }}>
          Usage Insights
        </h1>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <KpiCard
            icon={<MessageSquare size={18} />}
            label="Total Chats"
            value={stats.system_metrics.total_chats.toLocaleString()}
          />
          <KpiCard
            icon={<Database size={18} />}
            label="Total Messages"
            value={stats.system_metrics.total_messages.toLocaleString()}
          />
          <KpiCard
            icon={<Clock size={18} />}
            label="Avg Query Latency"
            value={`${stats.system_metrics.avg_query_latency_ms || 0} ms`}
          />
          <KpiCard
            icon={<Zap size={18} />}
            label="Avg LLM Latency"
            value={`${stats.system_metrics.avg_llm_latency_ms || 0} ms`}
          />
        </div>

        {stats.openrouter.limit !== null && (
          <div className="mb-8 p-4 rounded-xl" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
            <h2 className="text-sm font-medium mb-4 uppercase tracking-wider flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
              <Activity size={14} /> OpenRouter Credits ({stats.openrouter.label})
            </h2>
            <div className="flex items-end gap-4">
              <div className="text-3xl font-semibold" style={{ color: "var(--color-text-primary)" }}>
                ${(stats.openrouter.usage || 0).toFixed(4)}
              </div>
              <div className="text-sm mb-1" style={{ color: "var(--color-text-secondary)" }}>
                used of ${(stats.openrouter.limit || 0).toFixed(2)} limit
              </div>
            </div>
            {/* Progress bar */}
            <div className="w-full h-2 rounded-full mt-4" style={{ background: "var(--color-border-secondary)" }}>
              <div 
                className="h-full rounded-full bg-blue-500" 
                style={{ width: `${Math.min(100, ((stats.openrouter.usage || 0) / (stats.openrouter.limit || 1)) * 100)}%` }} 
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="p-5 rounded-xl" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
            <h2 className="text-sm font-medium mb-4 uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Token Usage by Project</h2>
            {stats.token_usage_by_project && stats.token_usage_by_project.length > 0 ? (
              <div className="h-[250px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.token_usage_by_project} layout="vertical" margin={{ left: 0, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border-secondary)" />
                    <XAxis type="number" stroke="var(--color-text-tertiary)" fontSize={12} />
                    <YAxis dataKey="project_name" type="category" width={120} stroke="var(--color-text-tertiary)" fontSize={12} />
                    <Tooltip cursor={{ fill: "var(--color-background-primary)" }} contentStyle={{ background: "var(--color-background-primary)", borderColor: "var(--color-border-secondary)", borderRadius: 8, color: "var(--color-text-primary)" }} />
                    <Bar dataKey="total_tokens" name="Tokens" fill="var(--color-text-success)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-sm" style={{ color: "var(--color-text-tertiary)" }}>No token usage data yet.</div>
            )}
          </div>

          <div className="p-5 rounded-xl flex flex-col" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
            <h2 className="text-sm font-medium mb-4 uppercase tracking-wider flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
              <AlertTriangle size={14} className="text-amber-500" /> Recent Hallucinations (Faithfulness)
            </h2>
            <div className="flex-1 overflow-y-auto">
              {hallucinations.length > 0 ? (
                <div className="space-y-4">
                  {hallucinations.map((log: any) => (
                    <div key={log.id} className="p-3 rounded-lg border border-white/5 bg-white/5">
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex flex-col gap-1">
                          <span className="text-xs font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-500 w-fit">
                            Score: {(log.score * 100).toFixed(0)}%
                          </span>
                          {log.project_name && (
                            <span className="text-[10px] opacity-60 flex items-center gap-1" style={{ color: "var(--color-text-secondary)" }}>
                              <Folder size={8} /> {log.project_name}
                            </span>
                          )}
                        </div>
                        <a href={`/chat/${log.chat_id}`} className="text-xs flex items-center gap-1 text-blue-400 hover:underline">
                          View Chat <ExternalLink size={10} />
                        </a>
                      </div>
                      <p className="text-xs line-clamp-2 mb-2" style={{ color: "var(--color-text-secondary)" }}>
                        {log.message_content}
                      </p>
                      {log.reason && (
                        <p className="text-[10px] italic" style={{ color: "var(--color-text-tertiary)" }}>
                          Reason: {log.reason}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-sm" style={{ color: "var(--color-text-tertiary)" }}>
                  No hallucinations detected.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="p-5 rounded-xl" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
            <h2 className="text-sm font-medium mb-4 uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Top Active Projects</h2>
            {stats.top_projects && stats.top_projects.length > 0 ? (
              <div className="h-[250px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.top_projects} layout="vertical" margin={{ left: 0, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border-secondary)" />
                    <XAxis type="number" stroke="var(--color-text-tertiary)" fontSize={12} />
                    <YAxis dataKey="name" type="category" width={120} stroke="var(--color-text-tertiary)" fontSize={12} />
                    <Tooltip cursor={{ fill: "var(--color-background-primary)" }} contentStyle={{ background: "var(--color-background-primary)", borderColor: "var(--color-border-secondary)", borderRadius: 8, color: "var(--color-text-primary)" }} />
                    <Bar dataKey="value" name="Messages" fill="var(--color-text-info)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-sm" style={{ color: "var(--color-text-tertiary)" }}>No project data available.</div>
            )}
          </div>

          <div className="p-5 rounded-xl" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
            <h2 className="text-sm font-medium mb-4 uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>Most Queried Files</h2>
            {stats.top_sources && stats.top_sources.length > 0 ? (
              <div className="h-[250px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats.top_sources} layout="vertical" margin={{ left: 0, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border-secondary)" />
                    <XAxis type="number" stroke="var(--color-text-tertiary)" fontSize={12} />
                    <YAxis dataKey="name" type="category" width={120} stroke="var(--color-text-tertiary)" fontSize={12} />
                    <Tooltip cursor={{ fill: "var(--color-background-primary)" }} contentStyle={{ background: "var(--color-background-primary)", borderColor: "var(--color-border-secondary)", borderRadius: 8, color: "var(--color-text-primary)" }} />
                    <Bar dataKey="value" name="Attachments/Links" fill="var(--color-text-warning)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-sm" style={{ color: "var(--color-text-tertiary)" }}>No source data available.</div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

function KpiCard({ icon, label, value }: { icon: React.ReactNode, label: string, value: string | number }) {
  return (
    <div className="p-4 rounded-xl flex items-center gap-4" style={{ border: "1px solid var(--color-border-secondary)", background: "var(--color-background-secondary)" }}>
      <div className="p-3 rounded-lg" style={{ background: "var(--color-background-primary)", color: "var(--color-text-secondary)" }}>
        {icon}
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-widest mb-1" style={{ color: "var(--color-text-tertiary)" }}>{label}</div>
        <div className="text-xl font-semibold" style={{ color: "var(--color-text-primary)" }}>{value}</div>
      </div>
    </div>
  );
}
