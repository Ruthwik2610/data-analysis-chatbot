import { useEffect, useState, type CSSProperties } from "react";
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
import { Activity, AlertTriangle, Clock, Database, MessageSquare, Zap, ExternalLink, Folder, TrendingUp, LayoutGrid, FileText, Cpu, HardDrive, Trash2 } from "lucide-react";

const textPrimary: CSSProperties = { color: "var(--color-text-primary)" };
const textSecondary: CSSProperties = { color: "var(--color-text-secondary)" };
const textTertiary: CSSProperties = { color: "var(--color-text-tertiary)" };
const panelStyle: CSSProperties = {
  background: "var(--color-background-elevated)",
  border: "1px solid var(--color-border-secondary)",
  boxShadow: "var(--shadow-sm)",
};
const panelSubtleStyle: CSSProperties = {
  background: "var(--color-background-secondary)",
  border: "1px solid var(--color-border-secondary)",
};
const chartGridColor = "var(--color-border-tertiary)";
const chartAxisColor = "var(--color-text-tertiary)";
const chartCursor = { fill: "var(--color-background-secondary)" };
const chartTooltipStyle: CSSProperties = {
  background: "var(--color-background-elevated)",
  border: "1px solid var(--color-border-secondary)",
  borderRadius: 12,
  color: "var(--color-text-primary)",
  fontSize: 10,
  fontWeight: "bold",
};

export function AdminDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [hallucinations, setHallucinations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [clearingCache, setClearingCache] = useState(false);
  const [maintenanceMsg, setMaintenanceMsg] = useState("");

  const loadData = () => {
    Promise.all([
      api.getAdminStats(),
      api.getHallucinations()
    ])
      .then(([statsData, halData]) => {
        setStats(statsData);
        setHallucinations(halData);
      })
      .catch(console.error)
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleClearCache = async () => {
    if (!confirm("Are you sure you want to clear all cached files? This will free up space but may slow down initial queries.")) return;
    setClearingCache(true);
    try {
        const res = await api.clearCache();
        setMaintenanceMsg(res.message);
        loadData();
        setTimeout(() => setMaintenanceMsg(""), 5000);
    } catch (err) {
        alert("Failed to clear cache");
    } finally {
        setClearingCache(false);
    }
  };

  if (loading) {
    return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 bg-primary h-screen">
            <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin" />
            <div className="text-sm font-bold uppercase tracking-widest" style={textTertiary}>Synthesizing Insights...</div>
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
                <h1 className="text-2xl font-semibold" style={textPrimary}>System Insights</h1>
                <p className="text-xs font-medium" style={textSecondary}>Core performance metrics and usage analytics</p>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest" style={{ ...panelSubtleStyle, ...textSecondary }}>
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
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                <LayoutGrid size={12} /> VPS Infrastructure Health
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-8 rounded-[32px]" style={panelStyle}>
                <HealthMetric 
                    label="CPU Load" 
                    value={`${stats.system_health?.cpu_percent || 0}%`} 
                    percent={stats.system_health?.cpu_percent || 0}
                    icon={<Cpu size={16} />}
                    color="blue"
                    warning={stats.system_health?.cpu_percent > 80}
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
                    warning={stats.system_health?.disk_percent > 90}
                />
            </div>
        </div>

        {/* Maintenance (New) */}
        <div className="flex flex-col gap-4">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                <LayoutGrid size={12} /> System Maintenance
            </h3>
            <div className="p-8 rounded-[32px] flex flex-col gap-6" style={panelStyle}>
                <div className="flex items-center justify-between">
                    <div className="flex flex-col gap-1">
                        <div className="text-sm font-semibold" style={textPrimary}>System Cache</div>
                        <div className="text-[10px] font-medium uppercase tracking-widest" style={textTertiary}>Clear temporary files and free up disk space</div>
                    </div>
                    <button 
                        onClick={handleClearCache}
                        disabled={clearingCache}
                        className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all"
                        style={clearingCache
                          ? { ...panelSubtleStyle, color: "var(--color-text-tertiary)", opacity: 0.65 }
                          : { background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.22)", color: "#dc2626" }}
                    >
                        {clearingCache ? <div className="w-3 h-3 rounded-full animate-spin" style={{ border: "2px solid var(--color-border-secondary)", borderTopColor: "var(--color-text-primary)" }} /> : <Trash2 size={14} />}
                        {clearingCache ? 'Clearing...' : 'Clear Cache'}
                    </button>
                </div>
                {maintenanceMsg && (
                    <div className="text-[10px] font-bold text-green-500 uppercase tracking-widest animate-in fade-in slide-in-from-left-2">
                        {maintenanceMsg}
                    </div>
                )}
            </div>
        </div>

        {/* Credit Tracker */}
        {stats.openrouter.limit !== null && (
          <div className="p-8 rounded-[32px] flex flex-col gap-6" style={panelStyle}>
            <div className="flex items-center justify-between">
                <h2 className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2" style={textTertiary}>
                    <TrendingUp size={12} /> Resource Allocation (OpenRouter)
                </h2>
                <span className="text-[10px] font-mono uppercase" style={textTertiary}>{stats.openrouter.label}</span>
            </div>
            
            <div className="flex items-end gap-4">
              <div className="text-4xl font-bold" style={textPrimary}>
                ${(stats.openrouter.usage || 0).toFixed(4)}
              </div>
              <div className="text-xs font-medium mb-1.5 uppercase tracking-widest" style={textTertiary}>
                of ${(stats.openrouter.limit || 0).toFixed(2)} monthly quota
              </div>
            </div>

            <div className="relative w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--color-background-secondary)" }}>
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
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                    <Zap size={12} /> Consumption by Project
                </h3>
                <div className="p-6 rounded-[32px] min-h-[300px]" style={panelStyle}>
                    {stats.token_usage_by_project && stats.token_usage_by_project.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.token_usage_by_project} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={chartGridColor} />
                                <XAxis type="number" hide />
                                <YAxis dataKey="project_name" type="category" width={100} stroke={chartAxisColor} fontSize={10} fontWeight="bold" />
                                <Tooltip 
                                    cursor={chartCursor}
                                    contentStyle={chartTooltipStyle}
                                />
                                <Bar dataKey="total_tokens" name="Tokens" fill="#3b82f6" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest" style={textTertiary}>No consumption data</div>
                    )}
                </div>
            </div>

            {/* Hallucination Feed */}
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-amber-500/60 flex items-center gap-2">
                    <AlertTriangle size={12} /> Faithfulness Alerts
                </h3>
                <div className="p-4 rounded-[32px] min-h-[300px] flex flex-col" style={panelStyle}>
                    {hallucinations.length > 0 ? (
                        <div className="flex-1 overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar">
                            {hallucinations.map((log: any) => (
                                <div key={log.id} className="p-4 rounded-2xl transition-all group" style={panelSubtleStyle}>
                                    <div className="flex justify-between items-start mb-2">
                                        <div className="flex flex-col gap-1">
                                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-500 w-fit uppercase tracking-wider">
                                                Score: {(log.score * 100).toFixed(0)}%
                                            </span>
                                            {log.project_name && (
                                                <span className="text-[9px] font-bold uppercase tracking-widest flex items-center gap-1" style={textTertiary}>
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
                                            <a href={`/?chat_id=${encodeURIComponent(log.chat_id)}`} className="p-2 rounded-lg hover:text-blue-400 transition-all opacity-0 group-hover:opacity-100" style={{ ...panelSubtleStyle, ...textTertiary }}>
                                                <ExternalLink size={12} />
                                            </a>
                                        </div>
                                    </div>
                                    <p className="text-xs font-medium line-clamp-1 mb-1" style={textSecondary}>
                                        "{log.message_content}"
                                    </p>
                                    {log.reason && (
                                        <p className="text-[9px] font-bold uppercase tracking-tighter" style={textTertiary}>
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
                            <p className="text-[10px] font-bold uppercase tracking-[0.2em]" style={textTertiary}>100% Faithful System</p>
                        </div>
                    )}
                </div>
            </div>
        </div>

        {/* Global Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                    <LayoutGrid size={12} /> Project Engagement
                </h3>
                <div className="p-6 rounded-[32px] min-h-[300px]" style={panelStyle}>
                    {stats.top_projects && stats.top_projects.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.top_projects} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={chartGridColor} />
                                <XAxis type="number" hide />
                                <YAxis dataKey="name" type="category" width={100} stroke={chartAxisColor} fontSize={10} fontWeight="bold" />
                                <Tooltip 
                                    cursor={chartCursor}
                                    contentStyle={chartTooltipStyle}
                                />
                                <Bar dataKey="value" name="Messages" fill="#6366f1" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest" style={textTertiary}>No engagement data</div>
                    )}
                </div>
            </div>

            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                    <FileText size={12} /> High-Traffic Sources
                </h3>
                <div className="p-6 rounded-[32px] min-h-[300px]" style={panelStyle}>
                    {stats.top_sources && stats.top_sources.length > 0 ? (
                        <div className="h-[250px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.top_sources} layout="vertical" margin={{ left: 0, right: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={chartGridColor} />
                                <XAxis type="number" hide />
                                <YAxis dataKey="name" type="category" width={100} stroke={chartAxisColor} fontSize={10} fontWeight="bold" />
                                <Tooltip
                                    cursor={chartCursor}
                                    contentStyle={chartTooltipStyle}
                                />
                                <Bar dataKey="value" name="Attachments" fill="#f59e0b" radius={[0, 8, 8, 0]} />
                            </BarChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[250px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest" style={textTertiary}>No traffic data</div>
                    )}
                </div>
            </div>
        </div>

        <div className="flex flex-col gap-4">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={textTertiary}>
                <Zap size={12} /> Token Spend by Purpose
            </h3>
            <div className="p-6 rounded-[32px] min-h-[220px]" style={panelStyle}>
                {stats.token_usage_by_purpose && stats.token_usage_by_purpose.length > 0 ? (
                    <div className="h-[180px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.token_usage_by_purpose}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartGridColor} />
                                <XAxis dataKey="purpose" stroke={chartAxisColor} fontSize={10} fontWeight="bold" />
                                <YAxis hide />
                                <Tooltip contentStyle={chartTooltipStyle} cursor={chartCursor} />
                                <Bar dataKey="total_tokens" name="Tokens" fill="#10b981" radius={[8, 8, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="h-[180px] flex items-center justify-center text-[10px] font-bold uppercase tracking-widest" style={textTertiary}>No token spend data</div>
                )}
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
            background: var(--color-border-secondary);
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
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest" style={textTertiary}>
                    {icon} {label}
                </div>
                <div className={`text-[10px] font-mono font-bold ${warning ? 'text-red-400' : ''}`} style={warning ? undefined : textSecondary}>
                    {value}
                </div>
            </div>
            <div className="relative w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--color-background-secondary)" }}>
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
        blue: "#2563eb",
        indigo: "#4f46e5",
        emerald: "#059669",
        amber: "#d97706",
    };
    const accent = colorMap[color] || colorMap.blue;

    return (
        <div className="p-6 rounded-[24px] flex flex-col gap-2 relative overflow-hidden group transition-all" style={panelStyle}>
            <div className={`absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity scale-150`}>
                {icon}
            </div>
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest" style={{ color: accent }}>
                {icon} {label}
            </div>
            <div className="text-3xl font-bold leading-none" style={textPrimary}>{value}</div>
            <div className="text-[10px] font-bold uppercase tracking-tighter" style={textTertiary}>{description}</div>
        </div>
    );
}
