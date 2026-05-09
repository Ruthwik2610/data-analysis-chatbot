"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { 
  Activity, 
  ExternalLink, 
  Search, 
  Filter, 
  AlertCircle, 
  CheckCircle2, 
  Clock,
  Zap,
  LayoutGrid,
  RefreshCw
} from "lucide-react";

interface Trace {
  id: string;
  query: string;
  trace_id: string;
  status: "success" | "error" | "hallucination";
  timestamp: number;
  phoenix_url: string;
}

export function ObservabilityDashboard() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [metrics, setMetrics] = useState<any>({
    avg_faithfulness: null,
    hallucination_count: 0,
    trace_volume: 0
  });
  const [projectName, setProjectName] = useState("data-analysis-chatbot");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isPolling, setIsPolling] = useState(true);

  const loadTraces = async () => {
    try {
      const data: any = await api.getTraces(50);
      setTraces(data.traces || []);
      if (data.config?.phoenix_project_name) {
          setProjectName(data.config.phoenix_project_name);
      }
      if (data.metrics) {
          setMetrics(data.metrics);
      }
    } catch (err) {
      console.error("Failed to fetch traces:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTraces();
    
    let interval: any;
    if (isPolling) {
      interval = setInterval(loadTraces, 5000); // Poll every 5 seconds
    }
    
    return () => clearInterval(interval);
  }, [isPolling]);

  const filteredTraces = traces.filter(t => {
    if (filter !== "all" && t.status !== filter) return false;
    if (searchQuery && !t.query.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto bg-primary custom-scrollbar">
      <div className="px-8 py-8 max-w-6xl mx-auto w-full flex flex-col gap-8">
        
        {/* Header Section */}
        <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-semibold text-white">Observability</h1>
                <p className="text-xs text-white/40 font-medium">Real-time LLM tracing and evaluation via Arize Phoenix</p>
            </div>
            <div className="flex items-center gap-3">
                <button 
                    onClick={() => setIsPolling(!isPolling)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all ${isPolling ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-white/5 text-white/40 border border-white/10'}`}
                >
                    <RefreshCw size={12} className={isPolling ? 'animate-spin' : ''} />
                    {isPolling ? 'Live Polling' : 'Paused'}
                </button>
                <a 
                    href={`https://app.phoenix.arize.com/projects/${projectName}`} 
                    target="_blank" 
                    rel="noreferrer"
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500 text-white text-xs font-bold hover:bg-blue-600 transition-all shadow-lg shadow-blue-500/20"
                >
                    Open Phoenix Cloud <ExternalLink size={14} />
                </a>
            </div>
        </div>

        {/* High-Level Eval Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <EvalCard 
                label="Faithfulness" 
                value={metrics.avg_faithfulness ? `${metrics.avg_faithfulness}%` : "N/A"} 
                status={metrics.avg_faithfulness > 90 ? "good" : metrics.avg_faithfulness > 70 ? "neutral" : "bad"} 
                description="Avg grounding score"
                icon={<CheckCircle2 size={16} />}
            />
            <EvalCard 
                label="Hallucinations" 
                value={metrics.hallucination_count.toString()} 
                status={metrics.hallucination_count === 0 ? "good" : metrics.hallucination_count < 5 ? "neutral" : "bad"} 
                description="Detected issues"
                icon={<AlertCircle size={16} />}
            />
            <EvalCard 
                label="Trace Volume" 
                value={metrics.trace_volume.toString()} 
                status="good" 
                description="Total spans captured"
                icon={<Zap size={16} />}
            />
        </div>

        {/* Embedded Visual (Placeholder for actual UMAP/Clustering iframe) */}
        <div className="flex flex-col gap-4">
            <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 text-white/40 flex items-center gap-2">
                <LayoutGrid size={12} /> Semantic Clusters (Embedding Space)
            </h3>
            <div className="w-full h-[300px] bg-white/[0.02] border border-white/5 rounded-[32px] overflow-hidden relative group">
                <div className="absolute inset-0 flex items-center justify-center bg-slate-900/40 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity z-10">
                    <p className="text-xs font-bold text-white bg-white/10 px-4 py-2 rounded-full border border-white/10">
                        Visualizing 1,240 Spans...
                    </p>
                </div>
                {/* Visual Placeholder: Grid of glowing dots */}
                <div className="grid grid-cols-12 gap-4 p-12 opacity-20">
                    {Array.from({ length: 48 }).map((_, i) => (
                        <div 
                            key={i} 
                            className={`w-2 h-2 rounded-full ${i % 7 === 0 ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-blue-400 opacity-40'}`}
                            style={{ 
                                marginTop: Math.sin(i) * 20,
                                marginLeft: Math.cos(i) * 20
                            }}
                        />
                    ))}
                </div>
            </div>
        </div>

        {/* Trace Stream */}
        <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between px-2">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40 flex items-center gap-2">
                    <Clock size={12} /> Live Trace Stream
                </h3>
                <div className="flex items-center gap-3">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20" size={14} />
                        <input 
                            type="text" 
                            placeholder="Search queries..." 
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="bg-white/5 border border-white/10 rounded-full pl-9 pr-4 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500/50 w-64"
                        />
                    </div>
                    <select 
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        className="bg-white/5 border border-white/10 rounded-full px-4 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500/50"
                    >
                        <option value="all">All Status</option>
                        <option value="success">Success</option>
                        <option value="hallucination">Hallucination</option>
                        <option value="error">Error</option>
                    </select>
                </div>
            </div>

            <div className="flex flex-col gap-3">
                {filteredTraces.map(trace => (
                    <TraceRow key={trace.id} trace={trace} />
                ))}
            </div>
        </div>

      </div>
    </div>
  );
}

function EvalCard({ label, value, description, status, icon }: any) {
    const color = status === "good" ? "text-green-400" : status === "neutral" ? "text-amber-400" : "text-red-400";
    const bg = status === "good" ? "bg-green-400/10" : status === "neutral" ? "bg-amber-400/10" : "bg-red-400/10";

    return (
        <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2">
            <div className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest ${color}`}>
                {icon} {label}
            </div>
            <div className="text-3xl font-bold text-white">{value}</div>
            <div className="text-[10px] opacity-30 font-bold uppercase tracking-tighter">{description}</div>
        </div>
    );
}

function TraceRow({ trace }: { trace: Trace }) {
    const statusColors = {
        success: "bg-green-500/10 text-green-500 border-green-500/20",
        hallucination: "bg-amber-500/10 text-amber-500 border-amber-500/20",
        error: "bg-red-500/10 text-red-500 border-red-500/20"
    };

    const formattedTime = new Date(trace.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const formattedDate = new Date(trace.timestamp * 1000).toLocaleDateString();

    return (
        <div className="group flex items-center justify-between p-4 rounded-2xl bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] transition-all">
            <div className="flex items-center gap-4 flex-1">
                <div className={`w-2 h-12 rounded-full ${trace.status === 'success' ? 'bg-green-500' : trace.status === 'hallucination' ? 'bg-amber-500' : 'bg-red-500'} opacity-20`} />
                <div className="flex flex-col gap-1 max-w-xl">
                    <p className="text-sm text-white font-medium line-clamp-1">{trace.query}</p>
                    <div className="flex items-center gap-3">
                        <span className="text-[10px] font-mono text-white/30">{trace.trace_id.substring(0, 8)}...</span>
                        <span className="text-[10px] font-bold uppercase tracking-widest text-white/20">•</span>
                        <span className="text-[10px] font-bold uppercase tracking-widest text-white/30">{formattedDate} {formattedTime}</span>
                    </div>
                </div>
            </div>
            <div className="flex items-center gap-4">
                <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border ${statusColors[trace.status]}`}>
                    {trace.status}
                </span>
                <a 
                    href={trace.phoenix_url} 
                    target="_blank" 
                    rel="noreferrer"
                    className="p-2 rounded-xl bg-white/5 text-white/40 hover:text-white hover:bg-blue-500/20 transition-all opacity-0 group-hover:opacity-100"
                    title="Deep Trace in Phoenix"
                >
                    <ExternalLink size={14} />
                </a>
            </div>
        </div>
    );
}
