"use client";

import React, { useMemo } from "react";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, 
  LineChart, Line, AreaChart, Area 
} from "recharts";
import { TrendingUp, BarChart3, Activity, Target } from "lucide-react";

interface RunStats {
  id: string;
  created_at: number;
  stats: {
    pass: number;
    fail: number;
    partial: number;
    error: number;
  };
  snapshot?: {
    model?: string;
    agent_model?: string;
    data_sources?: string[];
  };
}

interface TestingDashboardProps {
  runs: RunStats[];
}

export default function TestingDashboard({ runs }: TestingDashboardProps) {
  // Transform runs for charting (reverse to show chronological order)
  const chartData = useMemo(() => {
    return [...runs].reverse().map(run => ({
      name: new Date(run.created_at * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      pass: run.stats?.pass || 0,
      fail: run.stats?.fail || 0,
      partial: run.stats?.partial || 0,
      error: run.stats?.error || 0,
      total: (run.stats?.pass || 0) + (run.stats?.fail || 0) + (run.stats?.partial || 0) + (run.stats?.error || 0),
      timestamp: run.created_at,
      model: run.snapshot?.model || "Unknown",
    }));
  }, [runs]);

  const latestStats = chartData[chartData.length - 1];
  const passRate = latestStats && latestStats.total > 0 
    ? ((latestStats.pass / latestStats.total) * 100).toFixed(1) 
    : "0.0";

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-slate-900 border border-white/10 p-4 rounded-xl shadow-2xl backdrop-blur-md">
          <p className="text-[10px] font-bold uppercase tracking-widest text-white/40 mb-2">{label}</p>
          <div className="flex flex-col gap-1.5">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center justify-between gap-8">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                  <span className="text-xs text-white/70 capitalize">{entry.name}</span>
                </div>
                <span className="text-xs font-bold text-white">{entry.value}</span>
              </div>
            ))}
            <div className="h-px bg-white/5 my-1" />
            <div className="flex items-center justify-between gap-8">
                <span className="text-[10px] uppercase font-bold text-blue-400">Model</span>
                <span className="text-[10px] font-mono text-white/50">{data.model}</span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="flex flex-col gap-8 w-full animate-in fade-in slide-in-from-bottom-4 duration-1000">
      {/* Top Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
         <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-green-500">
                <Target size={12} /> Reliability
            </div>
            <div className="flex items-end gap-2">
                <div className="text-3xl font-bold">{passRate}%</div>
                <div className="text-[10px] font-bold text-green-500 mb-1 flex items-center gap-0.5">
                    <TrendingUp size={10} /> +2.4%
                </div>
            </div>
            <div className="text-[10px] opacity-30 font-bold uppercase tracking-tighter">Pass rate on latest run</div>
         </div>
         
         <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-blue-500">
                <Activity size={12} /> Total Eval
            </div>
            <div className="text-3xl font-bold">{runs.reduce((acc, r) => acc + (r.stats?.pass || 0) + (r.stats?.fail || 0), 0)}</div>
            <div className="text-[10px] opacity-30 font-bold uppercase tracking-tighter">Queries evaluated across all runs</div>
         </div>

         <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-orange-500">
                <TrendingUp size={12} /> Partial Avg
            </div>
            <div className="text-3xl font-bold">
                {chartData.length > 0 ? (chartData.reduce((acc, d) => acc + d.partial, 0) / chartData.length).toFixed(1) : 0}
            </div>
            <div className="text-[10px] opacity-30 font-bold uppercase tracking-tighter">Average partial scores per run</div>
         </div>

         <div className="p-6 rounded-[24px] bg-white/[0.03] border border-white/5 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-purple-500">
                <BarChart3 size={12} /> Version Count
            </div>
            <div className="text-3xl font-bold">{runs.length}</div>
            <div className="text-[10px] opacity-30 font-bold uppercase tracking-tighter">Snapshotted configurations</div>
         </div>
      </div>

      {/* Main Chart */}
      <div className="flex flex-col gap-4">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
            <TrendingUp size={12} /> Performance Trend (Pass vs Fail)
        </h3>
        <div className="w-full h-[350px] bg-white/[0.02] border border-white/5 rounded-[32px] p-8">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                        <linearGradient id="colorPass" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0}/>
                        </linearGradient>
                        <linearGradient id="colorFail" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis 
                        dataKey="name" 
                        axisLine={false} 
                        tickLine={false} 
                        tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10, fontWeight: 700 }}
                        dy={10}
                    />
                    <YAxis 
                        axisLine={false} 
                        tickLine={false} 
                        tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10, fontWeight: 700 }}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Area 
                        type="monotone" 
                        dataKey="pass" 
                        stroke="#22c55e" 
                        strokeWidth={3}
                        fillOpacity={1} 
                        fill="url(#colorPass)" 
                    />
                    <Area 
                        type="monotone" 
                        dataKey="fail" 
                        stroke="#ef4444" 
                        strokeWidth={3}
                        fillOpacity={1} 
                        fill="url(#colorFail)" 
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
      </div>

      {/* Breakdown Bar Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="flex flex-col gap-4">
              <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
                  <BarChart3 size={12} /> Latest Run Distribution
              </h3>
              <div className="w-full h-[250px] bg-white/[0.02] border border-white/5 rounded-[32px] p-8 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={latestStats ? [latestStats] : []}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                          <XAxis hide />
                          <YAxis axisLine={false} tickLine={false} tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} />
                          <Tooltip content={<CustomTooltip />} />
                          <Bar dataKey="pass" fill="#22c55e" radius={[4, 4, 0, 0]} barSize={40} />
                          <Bar dataKey="partial" fill="#f97316" radius={[4, 4, 0, 0]} barSize={40} />
                          <Bar dataKey="fail" fill="#ef4444" radius={[4, 4, 0, 0]} barSize={40} />
                          <Bar dataKey="error" fill="#a855f7" radius={[4, 4, 0, 0]} barSize={40} />
                      </BarChart>
                  </ResponsiveContainer>
              </div>
          </div>

          <div className="flex flex-col gap-4">
              <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
                  <Activity size={12} /> Version Comparisons
              </h3>
              <div className="flex-1 bg-white/[0.02] border border-white/5 rounded-[32px] p-6 flex flex-col gap-4 overflow-y-auto custom-scrollbar max-h-[250px]">
                  {runs.slice(0, 5).map((run, i) => (
                      <div key={run.id} className="flex items-center justify-between p-4 rounded-2xl bg-white/5 border border-white/5 group">
                          <div className="flex flex-col gap-1">
                              <span className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                                  {new Date(run.created_at * 1000).toLocaleString()}
                              </span>
                              <span className="text-xs font-mono opacity-60 truncate max-w-[150px]">
                                  {run.snapshot?.model || "Standard Model"}
                              </span>
                          </div>
                          <div className="flex items-center gap-4">
                              <div className="flex flex-col items-end">
                                  <span className="text-xs font-bold text-green-500">
                                      {run.stats?.pass || 0} Pass
                                  </span>
                                  <span className="text-[9px] opacity-30 font-bold uppercase">
                                      {(((run.stats?.pass || 0) / ((run.stats?.pass || 0) + (run.stats?.fail || 0) || 1)) * 100).toFixed(0)}%
                                  </span>
                              </div>
                          </div>
                      </div>
                  ))}
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
          background: rgba(255,255,255,0.1);
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
}
