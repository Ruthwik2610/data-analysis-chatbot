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
} from "recharts";
import { Activity, Clock, Database, MessageSquare, Zap } from "lucide-react";

export function AdminDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    api.getAdminStats()
      .then((data) => {
        if (mounted) setStats(data);
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
