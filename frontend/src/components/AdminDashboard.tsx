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
import { Activity, AlertTriangle, Clock, Database, MessageSquare, Zap, ExternalLink, Folder, TrendingUp, LayoutGrid, FileText, Cpu, HardDrive } from "lucide-react";

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
        <div className="flex-1 flex flex-col items-center justify-center gap-4 bg-primary h-screen">
            <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin" />
            <div className="text-sm font-bold uppercase tracking-widest text-white/20">Synthesizing Insights...</div>
        </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex-1 flex items-center justify-center text-red-500 bg-primary h-screen">
        Failed to load insights.
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto bg-primary custom-scrollbar">
      <div className="px-8 py-8 max-w-6xl mx-auto w-full flex flex-col gap-8">
        
        {/* Header Section */}
        <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-semibold text-white">System Insights</h1>
                <p className="text-xs text-white/40 font-medium">Core performance metrics and usage analytics</p>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-white/40 text-[10px] font-bold uppercase tracking-widest">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" /> Live Status
            </div>
        </div>

        {/* Top-Level KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <InsightCard 
                label="Total Activity" 
                value={stats.system_metrics.total_chats.toLocaleString()} 
                description="Unique chat sessions"
                icon={<MessageSquare size={16} />}
                color="blue"
            />
            <InsightCard 
                label="Data Scale" 
                value={stats.system_metrics.total_messages.toLocaleString()} 
                description="Total message turns"
                icon={<Database size={16} />}
                color="indigo"
            />
            <InsightCard 
                label="Engine Speed" 
                value={`${stats.system_metrics.avg_query_latency_ms || 0}ms`} 
                description="Avg local processing"
                icon={<Clock size={16} />}
                color="emerald"
            />
            <InsightCard 
                label="LLM Response" 
                value={`${stats.system_metrics.avg_llm_latency_ms || 0}ms`} 
                description="Avg remote inference"
                icon={<Zap size={16} />}
                color="amber"
            />
        </div>

        {/* VPS Health (New) */}
        <div className="flex flex-col gap-4">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-white/40 flex items-center gap-2">
                <LayoutGrid size={12} /> VPS Infrastructure Health
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-8 rounded-[32px] bg-white/[0.03] border border-white/5 shadow-xl">
                <HealthMetric 
                    label="CPU Load" 
                    value={`${stats.system_health?.cpu_percent || 0}%`} 
                    percent={stats.system_health?.cpu_percent || 0}
                    icon={<Cpu size={16} />}
                    color="blue"
                />
                <HealthMetric 
                    label="RAM Usage" 
                    value={`${stats.system_health?.ram_used_gb || 0}GB / ${stats.system_health?.ram_total_gb || 4}GB`} 
                    percent={stats.system_health?.ram_percent || 0}
                    icon={<Activity size={16} />}
                    color="emerald"
                    warning={stats.system_health?.ram_percent > 85}
                />
                <HealthMetric 
                    label="Disk Space" 
                    value={`${stats.system_health?.disk_free_gb || 0}GB Free`} 
                    percent={100 - (stats.system_health?.disk_percent || 0)}
                    icon={<HardDrive size={16} />}
                    color="indigo"
                />
            </div>
        </div>

        {/* Credit Tracker */}
        {stats.openrouter.limit !== null && (
          <div className="p-8 rounded-[32px] bg-white/[0.03] border border-white/5 flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <h2 className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40 flex items-center gap-2">
                    <TrendingUp size={12} /> Resource Allocation (OpenRouter)
                </h2>
                <span className="text-[10px] font-mono text-white/20 uppercase">{stats.openrouter.label}</span>
            </div>
            
            <div className="flex items-end gap-4">
              <div className="text-4xl font-bold text-white">
                ${(stats.openrouter.usage || 0).toFixed(4)}
              </div>
              <div className="text-xs font-medium text-white/30 mb-1.5 uppercase tracking-widest">
                of ${(stats.openrouter.limit || 0).toFixed(2)} monthly quota
              </div>
            </div>

            <div className="relative w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
              <div 
                className="absolute inset-y-0 left-0 bg-blue-500 rounded-full transition-all duration-1000 shadow-[0_0_10px_rgba(59,130,246,0.5)]" 
                style={{ width: `${Math.min(100, ((stats.openrouter.usage || 0) / (stats.openrouter.limit || 1)) * 100)}%` }} 
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Token Consumption */}
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-white/40 flex items-center gap-2">
                    <Zap size={12} /> Consumption by Project
                </h3>
                <div className="p-6 rounded-[32px] bg-white/[0.02] border border-white/5 min-h-[300px]">
                    {stats.token_usage_by_project && stats.token_usage_by_project.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.token_usage_by_project} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.05)" />
                                <XAxis type="number" hide />
                                <YAxis dataKey="project_name" type="category" width={100} stroke="rgba(255,255,255,0.3)" fontSize={10} fontWeight="bold" />
                                <Tooltip 
                                    cursor={{ fill: "rgba(255,255,255,0.02)" }} 
                                    contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, fontSize: 10, fontWeight: "bold" }} 
                                />
                                <Bar dataKey="total_tokens" name="Tokens" fill="#3b82f6" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest text-white/10">No consumption data</div>
                    )}
                </div>
            </div>

            {/* Hallucination Feed */}
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-amber-500/60 flex items-center gap-2">
                    <AlertTriangle size={12} /> Faithfulness Alerts
                </h3>
                <div className="p-4 rounded-[32px] bg-white/[0.02] border border-white/5 min-h-[300px] flex flex-col">
                    {hallucinations.length > 0 ? (
                        <div className="flex-1 overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar">
                            {hallucinations.map((log: any) => (
                                <div key={log.id} className="p-4 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/[0.08] transition-all group">
                                    <div className="flex justify-between items-start mb-2">
                                        <div className="flex flex-col gap-1">
                                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-500 w-fit uppercase tracking-wider">
                                                Score: {(log.score * 100).toFixed(0)}%
                                            </span>
                                            {log.project_name && (
                                                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 flex items-center gap-1">
                                                    <Folder size={8} /> {log.project_name}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {log.trace_id && (
                                                <a 
                                                    href={`https://app.phoenix.arize.com/projects/${stats.config?.phoenix_project_name || "data-analysis-chatbot"}/traces/${log.trace_id}`}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="p-2 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all opacity-0 group-hover:opacity-100"
                                                    title="Deep Trace"
                                                >
                                                    <Zap size={12} />
                                                </a>
                                            )}
                                            <a href={`/chat/${log.chat_id}`} className="p-2 rounded-lg bg-white/5 text-white/20 hover:text-blue-400 transition-all opacity-0 group-hover:opacity-100">
                                                <ExternalLink size={12} />
                                            </a>
                                        </div>
                                    </div>
                                    <p className="text-xs font-medium text-white/70 line-clamp-1 mb-1">
                                        "{log.message_content}"
                                    </p>
                                    {log.reason && (
                                        <p className="text-[9px] font-bold uppercase tracking-tighter text-white/20">
                                            Issue: {log.reason}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-center gap-4">
                            <div className="p-4 rounded-full bg-green-500/5 text-green-500/20">
                                <Activity size={32} strokeWidth={1} />
                            </div>
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/10">100% Faithful System</p>
                        </div>
                    )}
                </div>
            </div>
        </div>

        {/* Global Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-white/40 flex items-center gap-2">
                    <LayoutGrid size={12} /> Project Engagement
                </h3>
                <div className="p-6 rounded-[32px] bg-white/[0.02] border border-white/5 min-h-[300px]">
                    {stats.top_projects && stats.top_projects.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.top_projects} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.05)" />
                                <XAxis type="number" hide />
                                <YAxis dataKey="name" type="category" width={100} stroke="rgba(255,255,255,0.3)" fontSize={10} fontWeight="bold" />
                                <Tooltip 
                                    cursor={{ fill: "rgba(255,255,255,0.02)" }} 
                                    contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, fontSize: 10, fontWeight: "bold" }} 
                                />
                                <Bar dataKey="value" name="Messages" fill="#6366f1" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest text-white/10">No engagement data</div>
                    )}
                </div>
            </div>

            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-white/40 flex items-center gap-2">
                    <FileText size={12} /> High-Traffic Sources
                </h3>
                <div className="p-6 rounded-[32px] bg-white/[0.02] border border-white/5 min-h-[300px]">
                    {stats.top_sources && stats.top_sources.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.top_sources} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.05)" />
                                <XAxis type="number" hide />
                                <YAxis dataKey="name" type="category" width={100} stroke="rgba(255,255,255,0.3)" fontSize={10} fontWeight="bold" />
                                <Tooltip 
                                    cursor={{ fill: "rgba(255,255,255,0.02)" }} 
                                    contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, fontSize: 10, fontWeight: "bold" }} 
                                />
                                <Bar dataKey="value" name="Attachments" fill="#f59e0b" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest text-white/10">No traffic data</div>
                    )}
                </div>
            </div>
        </div>

      </div>

      <style jsx>{`
            .custom-scrollbar::-webkit-scrollbar {
            width: 4px;
            }
            .custom-scrollbar::-webkit-scrollbar-track {
            background: transparent;
            }
            .custom-scrollbar::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            }
        `}</style>
    </div>
  );
}

function HealthMetric({ icon, label, value, percent, color, warning }: any) {
    const colors: any = {
        blue: "bg-blue-500",
        emerald: "bg-emerald-500",
        indigo: "bg-indigo-500",
    };

    return (
        <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-white/40">
                    {icon} {label}
                </div>
                <div className={`text-[10px] font-mono font-bold ${warning ? 'text-red-400' : 'text-white/60'}`}>
                    {value}
                </div>
            </div>
            <div className="relative w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div 
                    className={`absolute inset-y-0 left-0 rounded-full transition-all duration-1000 ${warning ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]' : colors[color] + ' shadow-[0_0_10px_rgba(59,130,246,0.3)]'}`}
                    style={{ width: `${Math.min(100, percent)}%` }} 
                />
            </div>
        </div>
    );
}

function InsightCard({ icon, label, value, description, color }: any) {
    const colorMap: any = {
        blue: "text-blue-400 bg-blue-500/10 border-blue-500/20",
        indigo: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
        emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
        amber: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    };

    return (
        <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2 relative overflow-hidden group hover:bg-white/[0.05] transition-all">
            <div className={`absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity scale-150`}>
                {icon}
            </div>
            <div className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest ${colorMap[color].split(' ')[0]}`}>
                {icon} {label}
            </div>
            <div className="text-3xl font-bold text-white leading-none">{value}</div>
            <div className="text-[10px] font-bold uppercase tracking-tighter text-white/20">{description}</div>
        </div>
    );
}
